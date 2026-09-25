"""World and lifecycle operation handlers (sprint 011/05, WI3): the
`playthrough_service` wrappers for interacting with the world (`interact`,
item transfer, exits, adventures, hostility, leaving a scene) plus the
turn/run lifecycle operations (`RECORD_BEAT`, `COMPLETE_ACTION`,
`CLOSE_TURN`, `FINISH_RUN`).

`Handler` is redefined here rather than imported from `operations.py` to
avoid a circular import between the two sibling modules that both build the
combined registry (← WI3 brief). The two definitions must stay structurally
identical; `operations.py` owns the canonical one.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.llm import service as llm_service
from app.modules.playthrough import service as playthrough_service

from .flow_state import (
    ActionCursor,
    GameFlowState,
    NarrativeCursor,
    Operation,
    OperationKind,
    OperationResult,
    StateDelta,
    Usage,
    close_turn_state,
)


def _llm_usage(usage: Usage | None) -> llm_service.Usage | None:
    """← bug (sprint 08, WI3): `_record_beat` passed `state["usage"]`
    (`flow_state.Usage`, field `cost`) straight to `playthrough_service.
    record_narration`'s `usage`, which reads `llm_service.Usage`'s own
    `cost_usd`/`total_tokens` -- an `AttributeError` on every recorded
    beat that ever accumulated any usage at all."""
    if usage is None:
        return None
    return llm_service.Usage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.prompt_tokens + usage.completion_tokens,
        cost_usd=float(usage.cost) if usage.cost is not None else None,
    )


Handler = Callable[[Any, Operation, GameFlowState], Awaitable[tuple[OperationResult, StateDelta]]]


def roll_available(action: ActionCursor) -> bool:
    """True unless `action`'s own roll has already been spent (← AC4, roll
    ownership). `RESOLVE_CHECK` and `RESOLVE_SAVE` -- owned by
    `operations.py` -- must call this before applying `action.roll_id`;
    a consumed roll must refuse rather than reach the service layer twice."""
    return not action.roll_consumed


def _mutation_result(operation_id: str, result: Any) -> OperationResult:
    return OperationResult(
        operation_id=operation_id,
        status=result.status,
        reason=result.reason,
        event_ids=tuple(result.event_ids),
        value=dict(result.facts),
    )


async def _interact(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.interact(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=op.payload["actor_id"],
        object_id=op.payload["object_id"],
        action=op.payload["action"],
        roll_id=op.payload.get("roll_id"),
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _take_item(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.take(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=op.payload["actor_id"],
        item_id=op.payload["item_id"],
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _drop_item(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.drop(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=op.payload["actor_id"],
        item_id=op.payload["item_id"],
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _give_item(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.give(
        ctx.db,
        user_id=ctx.user_id,
        from_id=op.payload["from_id"],
        to_id=op.payload["to_id"],
        item_id=op.payload["item_id"],
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _use_exit(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.use_exit(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=op.payload["actor_id"],
        exit_id=op.payload["exit_id"],
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _enter_next_adventure(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.enter_next_adventure(
        ctx.db,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _set_hostility(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.set_hostility(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=op.payload["actor_id"],
        hostile=op.payload["hostile"],
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _leave_scene(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = await playthrough_service.leave_scene(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=op.payload["actor_id"],
        turn_id=state["turn"].turn_id,
    )
    return _mutation_result(op.operation_id, result), {}


async def _record_beat(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    event = await playthrough_service.record_narration(
        ctx.db,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        text=state["narrative"].draft,
        turn_id=state["turn"].turn_id,
        usage=_llm_usage(state["usage"]),
    )
    result = OperationResult(
        operation_id=op.operation_id,
        status="ok",
        reason=None,
        event_ids=(event.id,),
        value={},
    )
    delta: StateDelta = {
        "narrative": NarrativeCursor(
            beat_id=state["narrative"].beat_id, draft=None, event_id=event.id
        )
    }
    return result, delta


async def _complete_action(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    assert state["action"] is not None
    result = OperationResult(
        operation_id=op.operation_id, status="ok", reason=None, event_ids=(), value={}
    )
    action = state["action"]
    delta: StateDelta = {"action": ActionCursor(**{**action.__dict__, "status": "complete"})}
    return result, delta


async def _close_turn(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    result = OperationResult(
        operation_id=op.operation_id, status="ok", reason=None, event_ids=(), value={}
    )
    delta = close_turn_state(state)
    turn = state["turn"]
    delta["turn"] = type(turn)(**{**turn.__dict__, "status": "closed"})
    return result, delta


async def _finish_run(
    ctx: Any, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    mutation = await playthrough_service.finish_run(
        ctx.db,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        outcome=op.payload["outcome"],
        turn_id=state["turn"].turn_id,
    )
    result = _mutation_result(op.operation_id, mutation)
    turn = state["turn"]
    delta: StateDelta = {
        "turn": type(turn)(**{**turn.__dict__, "status": "terminal"}),
        "combat": None,
    }
    return result, delta


WORLD_HANDLERS: dict[OperationKind, Handler] = {
    OperationKind.INTERACT: _interact,
    OperationKind.TAKE_ITEM: _take_item,
    OperationKind.DROP_ITEM: _drop_item,
    OperationKind.GIVE_ITEM: _give_item,
    OperationKind.USE_EXIT: _use_exit,
    OperationKind.ENTER_NEXT_ADVENTURE: _enter_next_adventure,
    OperationKind.SET_HOSTILITY: _set_hostility,
    OperationKind.LEAVE_SCENE: _leave_scene,
    OperationKind.RECORD_BEAT: _record_beat,
    OperationKind.COMPLETE_ACTION: _complete_action,
    OperationKind.CLOSE_TURN: _close_turn,
    OperationKind.FINISH_RUN: _finish_run,
}
