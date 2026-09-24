"""`advance`'s pure scheduler (sprint 011/07, WI1) -- see `docs/general/
game-flow.v2.md`, "Scheduler priority". `select_next_effect` reads
`GameFlowState` and a fresh `Situation` and returns exactly one
`effects.NextEffect`; it never calls a model, rolls a die, interrupts or
writes to the database. The eight priorities are ordinary functions
(`advance_terminal` .. `validate_turn_close`), each `state, situation ->
NextEffect | None`, tried in order by `select_next_effect`; the first one
that returns non-`None` wins.

Two helpers exist for the caller (`agent/flow_nodes.py`, WI2/WI3) to apply
before or after calling this module, since this module itself never
mutates state:

- `guard_state(text)` -- when `select_next_effect` answers a fresh action
  turn with a guard refusal (`Operation(RECORD_BEAT)`), the node must
  first put the canned text into `state["narrative"].draft` with this
  helper, exactly as `narrate()` would have, before executing the
  operation.
- `resume_operation(awaiting, resume)` -- turns a checkpointed
  `ResumeResult` (from `await_player`'s `interrupt()`) into the operation
  that consumes it, or `None` when the response answers a request other
  than the one checkpointed. The node calls this once per resume, before
  `select_next_effect` runs again with `state["awaiting"]` cleared.
"""

import uuid
from collections.abc import Mapping
from typing import Any

from app.modules.playthrough.situation import Situation

from . import nodes
from .decisions import DecisionKind, DecisionRequest
from .effects import BeatRequest, NextEffect, Operation, PlayerWait, ResumeResult, TurnComplete
from .flow_state import (
    AwaitingRef,
    CombatCursor,
    GameFlowState,
    NarrativeCursor,
    OperationKind,
    OperationSpec,
)


def _new_id() -> str:
    return uuid.uuid4().hex


def guard_refusal(text: str | None) -> str | None:
    """The first `nodes.GUARD_PATTERNS` refusal `text` matches, or `None`.
    Imports the shared pattern list rather than copying its strings (←
    brief); `nodes.py` keeps owning them for the old graph."""
    if not text:
        return None
    for pattern, refusal in nodes.GUARD_PATTERNS:
        if pattern.search(text):
            return refusal
    return None


def guard_state(text: str) -> dict[str, Any]:
    """`StateDelta` the caller applies before executing the guard's
    `RECORD_BEAT` operation. Raises if `text` triggers no guard pattern --
    call only after `guard_refusal(text)` returned non-`None`."""

    refusal = guard_refusal(text)
    if refusal is None:
        raise ValueError("guard_state called for text that triggers no guard pattern")
    return {"narrative": NarrativeCursor(beat_id=_new_id(), draft=refusal, event_id=None)}


def player_roll_plan(
    *, actor_id: str, consumer: OperationKind, payload: Mapping[str, Any]
) -> tuple[OperationSpec, ...]:
    """Request roll → (wait/player-roll, off-plan, via `resume_operation`)
    → `consumer` (`RESOLVE_CHECK`/`RESOLVE_SAVE`) → complete action."""
    return (
        OperationSpec(
            kind=OperationKind.REQUEST_ROLL,
            payload={
                "actor_id": actor_id,
                "ability": payload.get("ability"),
                "skill": payload.get("skill"),
                "dc": payload.get("dc"),
                "kind": payload.get("kind", "ability_check"),
                "consumer": consumer.value,
                "consumer_payload": dict(payload),
            },
        ),
        OperationSpec(kind=consumer, payload={"dc": payload.get("dc")}),
        OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}),
    )


def attack_plan(
    *, actor_id: str, target_id: str, attack: str, is_player: bool
) -> tuple[OperationSpec, ...]:
    """Roll (player or monster) → resolve attack → complete action. A hit
    sets `pending_hit_id` (the `RESOLVE_ATTACK` handler's own job); the
    scheduler's `advance_hit` then preempts the plan's own `COMPLETE_ACTION`
    step with the damage fragment before it is ever reached. A miss simply
    falls through to `COMPLETE_ACTION`."""
    roll_step = (
        OperationSpec(
            kind=OperationKind.REQUEST_ROLL,
            payload={
                "actor_id": actor_id,
                "ability": "attack",
                "kind": "attack",
                "consumer": OperationKind.RESOLVE_ATTACK.value,
                "consumer_payload": {"target_id": target_id, "attack": attack},
            },
        )
        if is_player
        else OperationSpec(
            kind=OperationKind.ROLL_ACTOR,
            payload={"actor_id": actor_id, "kind": "attack"},
        )
    )
    return (
        roll_step,
        OperationSpec(
            kind=OperationKind.RESOLVE_ATTACK,
            payload={"actor_id": actor_id, "target_id": target_id, "attack": attack},
        ),
        OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}),
    )


def complete_action_plan(action_id: str) -> tuple[OperationSpec, ...]:
    return (OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={"action_id": action_id}),)


def resume_operation(awaiting: AwaitingRef, resume: ResumeResult) -> Operation | None:
    """A roll acknowledgement resumes as `ROLL_PLAYER`; a choice answer as
    `ACCEPT_CHOICE` carrying the answer text and, when the request named
    which move ref it fills, that ref's key under `"choice"`. A response
    naming a request other than the one checkpointed is rejected (`None`)
    rather than ever applied to the wrong request."""
    if resume.request_id != awaiting.request_id:
        return None
    if awaiting.kind == "roll":
        return Operation(operation_id=_new_id(), kind=OperationKind.ROLL_PLAYER, payload={})
    return Operation(
        operation_id=_new_id(),
        kind=OperationKind.ACCEPT_CHOICE,
        payload={"text": resume.value, "choice": awaiting.consumer_payload.get("choice")},
    )


def eligible_hostiles(situation: Situation, combat: CombatCursor | None) -> tuple[str, ...]:
    """Hostile, not down, alive, present in the scene. With no cursor yet,
    in `situation.actors` order. With one, in the cursor's own order,
    skipping every index already acted (`combat.index`'s own proof of who
    has gone -- no separate acted-set is kept)."""
    present = {actor.id: actor for actor in situation.actors}

    def _is_eligible(actor_id: str) -> bool:
        actor = present.get(actor_id)
        return actor is not None and actor.role == "hostile" and actor.is_alive and not actor.down

    if combat is None:
        return tuple(actor.id for actor in situation.actors if _is_eligible(actor.id))

    acted = set(combat.order[: combat.index])
    return tuple(
        actor_id for actor_id in combat.order if actor_id not in acted and _is_eligible(actor_id)
    )


def advance_terminal(state: GameFlowState, situation: Situation) -> NextEffect | None:
    hero_down = situation.hero.down or not situation.hero.is_alive
    turn = state["turn"]
    if not hero_down and turn.status != "terminal":
        return None
    if turn.status != "terminal":
        return Operation(
            operation_id=_new_id(),
            kind=OperationKind.FINISH_RUN,
            payload={"outcome": "defeat" if hero_down else "victory"},
        )
    narrative = state["narrative"]
    if narrative.draft is not None:
        return Operation(operation_id=_new_id(), kind=OperationKind.RECORD_BEAT, payload={})
    if narrative.event_id is None:
        return BeatRequest(beat_id=_new_id(), kind="closing", allowed_evidence_ids=(), payload={})
    return TurnComplete(status="terminal")


def advance_hit(state: GameFlowState, situation: Situation) -> NextEffect | None:
    hit_id = state["pending_hit_id"]
    if hit_id is None:
        return None
    move = state["move"]
    actor_id = (move.refs.get("actor_id") if move is not None else None) or situation.hero.id
    target_id = move.refs.get("target_id") if move is not None else None
    is_player = actor_id == situation.hero.id
    action = state["action"]
    has_damage_roll = action is not None and action.roll_id is not None and not action.roll_consumed
    if not has_damage_roll:
        if is_player:
            return Operation(
                operation_id=_new_id(),
                kind=OperationKind.REQUEST_ROLL,
                payload={
                    "actor_id": actor_id,
                    "ability": "damage",
                    "kind": "damage",
                    "consumer": OperationKind.APPLY_DAMAGE.value,
                    "consumer_payload": {"hit_id": hit_id, "target_id": target_id},
                },
            )
        return Operation(
            operation_id=_new_id(),
            kind=OperationKind.ROLL_ACTOR,
            payload={"actor_id": actor_id, "kind": "damage"},
        )
    return Operation(
        operation_id=_new_id(),
        kind=OperationKind.APPLY_DAMAGE,
        payload={"hit_id": hit_id, "target_id": target_id, "roll_id": action.roll_id},
    )


def advance_request(state: GameFlowState, situation: Situation) -> NextEffect | None:
    awaiting = state["awaiting"]
    if awaiting is None:
        return None
    return PlayerWait(
        request_id=awaiting.request_id, kind=awaiting.kind, public_payload=awaiting.public
    )


def advance_action(state: GameFlowState, situation: Situation) -> NextEffect | None:
    move = state["move"]
    action = state["action"]
    if action is None and move is None:
        refusal = guard_refusal(state["turn"].text)
        if refusal is not None:
            return Operation(operation_id=_new_id(), kind=OperationKind.RECORD_BEAT, payload={})
        return DecisionRequest(
            decision_id=_new_id(),
            kind=DecisionKind.READ_MOVE,
            evidence_ids=(),
            payload={"text": state["turn"].text},
        )
    if action is None:
        # A move is read but no plan has been reserved into an ActionCursor
        # yet -- building that cursor from the decision's proposed plan is
        # the `decide`/`execute` pipeline's own job (flow_nodes, WI2), not
        # an obligation this scheduler itself must resolve.
        return None
    if action.status in ("complete", "skipped"):
        return None
    if action.step_index >= len(action.plan):
        return Operation(
            operation_id=_new_id(),
            kind=OperationKind.COMPLETE_ACTION,
            payload={"action_id": action.action_id},
        )
    step = action.plan[action.step_index]
    return Operation(operation_id=_new_id(), kind=step.kind, payload=step.payload)


def advance_combat(state: GameFlowState, situation: Situation) -> NextEffect | None:
    combat = state["combat"]
    move = state["move"]
    hostiles = eligible_hostiles(situation, combat)

    if combat is None:
        if hostiles and move is not None and move.intent == "attack":
            return Operation(
                operation_id=_new_id(),
                kind=OperationKind.SETTLE_INITIATIVE,
                payload={
                    "scene_id": situation.scene_id,
                    "hero_ids": [situation.hero.id],
                    "hostile_ids": list(hostiles),
                },
            )
        return None

    if not hostiles:
        # Every eligible hostile in this round has already acted (or none
        # remain) -- nothing left for this priority; admitting the next
        # round or closing the fight belongs to a later sprint's runtime.
        return None

    actor_id = hostiles[0]
    return DecisionRequest(
        decision_id=_new_id(),
        kind=DecisionKind.MONSTER_ACTION,
        evidence_ids=(),
        payload={"actor_id": actor_id},
    )


def advance_reactions(state: GameFlowState, situation: Situation) -> NextEffect | None:
    reactions = state["reactions"]
    if not reactions:
        return None
    head = reactions[0]
    return DecisionRequest(
        decision_id=_new_id(),
        kind=DecisionKind.WORLD_REACTION,
        evidence_ids=(),
        payload={"reaction_id": head.reaction_id, "kind": head.kind, "payload": dict(head.payload)},
    )


def advance_narration(state: GameFlowState, situation: Situation) -> NextEffect | None:
    narrative = state["narrative"]
    if narrative.draft is not None:
        return Operation(operation_id=_new_id(), kind=OperationKind.RECORD_BEAT, payload={})
    action = state["action"]
    if action is not None and action.status == "complete" and narrative.event_id is None:
        return BeatRequest(beat_id=_new_id(), kind="outcome", allowed_evidence_ids=(), payload={})
    return None


def validate_turn_close(state: GameFlowState, situation: Situation) -> NextEffect:
    """Only reached once nothing earlier is owed -- re-checks every earlier
    priority itself, so a direct call (as the unit tests do) can never
    return `CLOSE_TURN` while an obligation remains."""
    for check in (
        advance_terminal,
        advance_hit,
        advance_request,
        advance_action,
        advance_combat,
        advance_reactions,
        advance_narration,
    ):
        effect = check(state, situation)
        if effect is not None:
            return effect
    turn = state["turn"]
    if turn.status == "closed":
        return TurnComplete(status="open")
    return Operation(operation_id=_new_id(), kind=OperationKind.CLOSE_TURN, payload={})


def select_next_effect(state: GameFlowState, situation: Situation) -> NextEffect:
    """The scheduler: the first non-`None` priority wins, `validate_turn_close`
    as the final fallback (← `docs/general/game-flow.v2.md`, "Scheduler priority")."""
    return validate_turn_close(state, situation)
