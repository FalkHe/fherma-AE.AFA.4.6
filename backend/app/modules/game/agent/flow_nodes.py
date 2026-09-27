"""The new flow's five graph nodes (sprint 011/07, WI2/WI3) -- plain async
`(state: GameFlowState) -> StateDelta` functions matching `docs/general/
game-flow.v2.md`, "The five node contracts". Not composed into a production
graph yet (sprint 08 does that); each is unit-tested at its own boundary.

Dependencies (`db`, `user_id`, `model`) come from a module-level
`FlowRuntime` set by `set_runtime()` -- sprint 08 sets it once per turn
before invoking the compiled graph; tests set it directly.

Failure handling, kept distinct on purpose:

- **Retryable model failures** (a transient provider error inside
  `decide()`/`narrate()`) are `core/llm`'s own `LlmError` family, already
  retried by `model_call.ainvoke()`/`llm_service.ainvoke_chat()`; a
  failure that survives those retries is infrastructure (see below).
- **Structured refusals** are ordinary data, never an exception: a
  `decisions.DecisionInvalid` that survives its own retry budget becomes
  `state["error"]` (an `ExecutionError`) with `state["effect"]` left
  alone, so the next `advance()` visit maps it to
  `TurnComplete("execution_error")` per the scheduler's own priority
  order. An `OperationResult(status="refused")` from `execute()` is
  likewise stored as a normal result, never raised.
- **Infrastructure failures** (a database error, a `LlmError` that
  exhausted its retries, a bug in this module) are not caught in
  `decide()`/`narrate()`/`await_player()` at all -- they propagate to the
  graph runtime exactly as raised, so a crashed turn resumes from its
  last checkpoint rather than silently losing the failure.
- **`execute()` is the one exception to that rule** (← live bug, run
  01M3H3EXQVF0X3BWGH2KVZ0YYW): a handler bug over model-shaped, not yet
  fully-validated payloads (a bad reference, a bad die roll, a bad `dc`)
  is common enough, and the resulting crash-then-replay-the-same-crash
  loop bad enough (every retry re-runs the very same handler over the
  same checkpointed state), that any exception a handler raises is caught
  there, logged, and turned into a `refused` `OperationResult` instead --
  see `execute()`'s own docstring. A true infrastructure failure (the
  database itself unreachable) still surfaces this way rather than
  vanishing, but it no longer wedges the run on a replay loop either: the
  plan step closes and the turn ends.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END
from langgraph.types import interrupt
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.playthrough import service as playthrough_service

from . import advance as advance_module
from . import decisions, narration, operations
from .decisions import DecisionContext, DecisionInvalid, DecisionRequest, DecisionResult
from .effects import BeatRequest, Operation, PlayerWait, ResumeResult, TurnComplete, add_usage
from .flow_state import (
    ActionCursor,
    ExecutionError,
    GameFlowState,
    Move,
    OperationResult,
    StateDelta,
)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlowRuntime:
    db: AsyncSession
    user_id: str
    model: BaseChatModel


_runtime: FlowRuntime | None = None


def set_runtime(runtime: FlowRuntime) -> None:
    """Set the module-level runtime every node reads from. Sprint 08 calls
    this once per turn before invoking the compiled graph; tests call it
    directly."""
    global _runtime
    _runtime = runtime


def get_runtime() -> FlowRuntime:
    if _runtime is None:
        raise RuntimeError("flow_nodes.set_runtime() was never called")
    return _runtime


async def _situation(state: GameFlowState) -> Any:
    runtime = get_runtime()
    return await playthrough_service.get_situation(
        runtime.db, user_id=runtime.user_id, run_id=state["turn"].run_id
    )


async def advance(state: GameFlowState) -> StateDelta:
    """The control-plane node: reloads a fresh `Situation`, reconciles a
    checkpointed `resume` response (if any) into the operation that
    consumes it or rejects it, applies a guard refusal's canned text, and
    stores exactly one `select_next_effect()` result.

    Sprint 08, WI3 adds the reconciliation steps that turn a `decide()`/
    `execute()` result into the next visit's `move`/`action`/`combat` --
    nothing previously consumed a `DecisionResult` at all (← bug, `agent/
    advance.py`'s own new docstrings). Each step both updates `delta`
    (what the graph checkpoints) and a local `working` copy of `state`
    (what `select_next_effect` reads this same visit), mirroring the
    resume path's own established shape."""
    situation = await _situation(state)
    delta: StateDelta = {}
    working: GameFlowState = dict(state)  # type: ignore[assignment]

    resume: ResumeResult | None = state.get("resume")
    if resume is not None:
        delta["resume"] = None
        working["resume"] = None
        awaiting = state["awaiting"]
        consuming_op = (
            advance_module.resume_operation(awaiting, resume) if awaiting is not None else None
        )
        if consuming_op is not None:
            delta["effect"] = consuming_op
            return delta
        # A stale response names a request other than the one checkpointed
        # -- rejected, not applied; `awaiting` stays set so the scheduler
        # re-emits the same `PlayerWait` below.

    opening_turn = working["turn"].input_kind == "opening" and working["turn"].status == "open"
    if opening_turn and working["move"] is None and working["action"] is None:
        # No player input to read a move from -- materialize a trivial,
        # already-`"complete"` action so `advance_narration` drafts the
        # opening beat straight away (← docs/general/game-flow.v2.
        # examples.md #1). `enter_adventure`/the passive check already ran
        # before the turn was ever taken (client-triggered, ← research).
        opening = {
            "move": Move(intent="opening", refs={}),
            "action": ActionCursor(
                action_id=uuid.uuid4().hex,
                actor_id=situation.hero.id,
                kind="opening",
                plan=(),
                step_index=0,
                status="complete",
                roll_id=None,
                roll_consumed=False,
            ),
        }
        working.update(opening)
        delta.update(opening)

    for step_delta in (
        advance_module.capture_check_outcome(working),
        advance_module.reconcile_step(working),
        advance_module.apply_choice_answer(working),
        advance_module.progress_combat(working, situation),
    ):
        if step_delta:
            working.update(step_delta)
            delta.update(step_delta)

    result = working.get("result")
    if isinstance(result, DecisionResult):
        decision_delta = advance_module.apply_decision(working, situation, result)
        working.update(decision_delta)
        delta.update(decision_delta)
        delta["result"] = None
        working["result"] = None
        if "effect" in decision_delta:
            # `apply_decision` already decided the next effect itself (an
            # ambiguous reference's `REQUEST_CHOICE`) -- `select_next_
            # effect` would only re-derive a stale one from `working`.
            return delta

    hero_action = advance_module.materialize_hero_action(working, situation)
    if hero_action:
        working.update(hero_action)
        delta.update(hero_action)

    delta["effect"] = advance_module.select_next_effect(working, situation)
    return delta


async def decide(state: GameFlowState) -> StateDelta:
    """One `decisions.decide()` call for the `DecisionRequest` in
    `state["effect"]`. A `DecisionInvalid` that survives its own retry
    budget is stored as `state["error"]`, leaving `effect` for `advance`
    to map to `TurnComplete("execution_error")`."""
    runtime = get_runtime()
    request: DecisionRequest = state["effect"]
    situation = await _situation(state)
    ctx = DecisionContext(
        db=runtime.db,
        user_id=runtime.user_id,
        run_id=state["turn"].run_id,
        hero_id=state["turn"].hero_id,
        situation=situation,
        model=runtime.model,
    )
    try:
        result = await decisions.decide(ctx, request, state)
    except DecisionInvalid as exc:
        return {
            "error": ExecutionError(code="decision_invalid", message=str(exc), operation_id=None)
        }
    return {"result": result, "usage": add_usage(state["usage"], result.usage)}


async def execute(state: GameFlowState) -> StateDelta:
    """One `operations.execute_operation()` call for the `Operation` in
    `state["effect"]`, against a fresh `Situation`. A refused operation
    stays an ordinary `OperationResult`.

    ← live bug (run 01M3H3EXQVF0X3BWGH2KVZ0YYW): a handler bug (there, a
    `None` `dc` reaching a bare `<=` chain) raised a plain `TypeError`
    that escaped this node entirely -- the turn 500'd, and every retry
    replayed and re-crashed the same node forever, since nothing ever
    closed the plan step that caused it. The contract-level holes that
    caused *this* crash are closed at their own boundary (`operations.
    invalid_dc_reason`, `playthrough.service._resolve_roll_outcome`'s own
    guard) -- this `try` is the backstop for the next one: any exception a
    handler raises is logged with its traceback and turned into an
    ordinary `refused` `OperationResult` instead, exactly like a handler
    that refuses on purpose (`operations._roll_actor`'s own `ValueError`
    catch). `advance.reconcile_step` already closes a refused plan step's
    action as `"complete"`, so the turn narrates an ordinary outcome and
    ends -- the player never sees anything but that the attempt did not
    resolve, and a retry of a run stuck on the old crash now runs this
    node fresh and moves past it instead of replaying the same raise."""
    runtime = get_runtime()
    op: Operation = state["effect"]
    situation = await _situation(state)
    ctx = operations.OperationContext(
        db=runtime.db,
        user_id=runtime.user_id,
        run_id=state["turn"].run_id,
        hero_id=state["turn"].hero_id,
        situation=situation,
    )
    try:
        result, op_delta = await operations.execute_operation(ctx, op, state)
    except Exception:
        _logger.exception(
            "operation handler raised",
            extra={"run_id": state["turn"].run_id, "operation_kind": op.kind.value},
        )
        await runtime.db.rollback()
        result = OperationResult(
            operation_id=op.operation_id,
            status="refused",
            reason="internal_error",
            event_ids=(),
            value={},
        )
        op_delta = {}
    delta: StateDelta = {"result": result}
    delta.update(op_delta)
    return delta


async def await_player(state: GameFlowState) -> StateDelta:
    """Nothing runs before the interrupt -- no database write, no model
    call, no random operation. On resume, stores the submitted response
    as a `ResumeResult` for `advance` to reconcile on the next visit."""
    wait: PlayerWait = state["effect"]
    value = interrupt(wait.public_payload)
    return {"resume": ResumeResult(request_id=wait.request_id, value=value)}


async def narrate(state: GameFlowState) -> StateDelta:
    """One `narration.narrate()` call for the `BeatRequest` in
    `state["effect"]`; stores the draft and accumulates usage."""
    runtime = get_runtime()
    request: BeatRequest = state["effect"]
    situation = await _situation(state)
    ctx = _NarrationContext(situation=situation, model=runtime.model)
    draft = await narration.narrate(ctx, request, state)
    delta = narration.draft_state(draft)
    delta["usage"] = add_usage(state["usage"], draft.usage)
    return delta


@dataclass(frozen=True)
class _NarrationContext:
    """Satisfies `narration.NarrationContext` by shape (← `narration.py`'s
    own docstring: kept local rather than imported)."""

    situation: Any
    model: BaseChatModel


def route_after_advance(state: GameFlowState) -> str:
    """Keyed only on `type(state["effect"])`, per `docs/general/
    game-flow.v2.md`: the router owns the mapping from effect type to
    graph node, nothing else about the effect's contents."""
    effect = state["effect"]
    if isinstance(effect, DecisionRequest):
        return "decide"
    if isinstance(effect, Operation):
        return "execute"
    if isinstance(effect, PlayerWait):
        return "await_player"
    if isinstance(effect, BeatRequest):
        return "narrate"
    if isinstance(effect, TurnComplete):
        return END
    raise TypeError(f"unrecognised effect type: {type(effect)!r}")
