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
from dataclasses import replace
from typing import Any

from app.modules.playthrough.situation import Situation

from . import nodes
from .decisions import (
    DecisionKind,
    DecisionRequest,
    DecisionResult,
    MonsterAction,
    ReadMoveDecision,
    ReferenceJudgement,
)
from .effects import BeatRequest, NextEffect, Operation, PlayerWait, ResumeResult, TurnComplete
from .flow_state import (
    ActionCursor,
    AwaitingRef,
    CombatCursor,
    GameFlowState,
    Move,
    NarrativeCursor,
    OperationKind,
    OperationResult,
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
    *, actor_id: str, target_id: str, attack: str, is_player: bool, item_id: str | None = None
) -> tuple[OperationSpec, ...]:
    """Roll (player or monster) → resolve attack → complete action. A hit
    sets `pending_hit_id` (the `RESOLVE_ATTACK` handler's own job); the
    scheduler's `advance_hit` then preempts the plan's own `COMPLETE_ACTION`
    step with the damage fragment before it is ever reached. A miss simply
    falls through to `COMPLETE_ACTION`.

    Both sides roll through `ROLL_ACTOR` (`playthrough_service.roll`),
    never `REQUEST_ROLL` (`request_player_roll`) -- ← bug (sprint 08,
    WI3): `request_player_roll` refuses `kind in ("attack", "damage")`
    outright, by that function's own contract ("an attack or damage
    roll, for any actor including the hero, goes through roll_dice"), so
    the player side's own `REQUEST_ROLL` step here always raised. The
    hero's own roll is simply visible (`visibility="player"`) rather than
    an interrupt the player must press through."""
    roll_step = OperationSpec(
        kind=OperationKind.ROLL_ACTOR,
        payload={
            "actor_id": actor_id,
            "kind": "attack",
            "context": {"attack": attack, "item_id": item_id},
            "visibility": "player" if is_player else "dm",
        },
    )
    resolve_payload: dict[str, Any] = {
        "actor_id": actor_id,
        "target_id": target_id,
        "attack": attack,
    }
    if item_id is not None:
        resolve_payload["item_id"] = item_id
    return (
        roll_step,
        OperationSpec(kind=OperationKind.RESOLVE_ATTACK, payload=resolve_payload),
        OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}),
    )


def complete_action_plan(action_id: str) -> tuple[OperationSpec, ...]:
    return (OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={"action_id": action_id}),)


def resume_operation(awaiting: AwaitingRef, resume: ResumeResult) -> Operation | None:
    """A roll acknowledgement resumes as `ROLL_PLAYER`; a choice answer as
    `ACCEPT_CHOICE` carrying the answer text and, when the request named
    which move ref it fills, that ref's key under `"ref_key"`. A response
    naming a request other than the one checkpointed is rejected (`None`)
    rather than ever applied to the wrong request.

    ← bug (sprint 08, WI3): this used to store the ref key under
    `payload["choice"]` -- the same payload key `operations.validate_refs`
    checks against *object* ids for an entirely different `Operation`
    shape (`decisions.py`'s own synthetic `INTERACT` validation for
    `JUDGE_REFERENCE`). A ref key such as `"target_id"` is never a known
    object id, so `execute_operation` refused every `ACCEPT_CHOICE`
    outright with `"stale_reference"` before `_accept_choice` ever ran."""
    if resume.request_id != awaiting.request_id:
        return None
    if awaiting.kind == "roll":
        return Operation(operation_id=_new_id(), kind=OperationKind.ROLL_PLAYER, payload={})
    return Operation(
        operation_id=_new_id(),
        kind=OperationKind.ACCEPT_CHOICE,
        payload={"text": resume.value, "ref_key": awaiting.consumer_payload.get("ref_key")},
    )


def reconcile_step(state: GameFlowState) -> dict[str, Any]:
    """Sprint 08, WI3 -- ← bug: nothing advanced `ActionCursor.step_index`
    after a plan step's own operation executed, so `advance_action` kept
    re-issuing the same step forever. Called by `flow_nodes.advance()` on
    every visit: when the last effect was the `Operation` for the
    action's current plan step and it reported `"ok"`, advances past it.
    An off-plan operation (`ROLL_PLAYER`, `ACCEPT_CHOICE`, a hit's own
    damage detour) never matches the step's own kind, so it never moves
    the cursor."""
    action = state["action"]
    effect = state["effect"]
    result = state["result"]
    if action is None or not isinstance(effect, Operation):
        return {}
    if not isinstance(result, OperationResult):
        return {}
    if action.step_index >= len(action.plan):
        return {}
    if action.plan[action.step_index].kind != effect.kind or result.status != "ok":
        return {}
    return {"action": replace(action, step_index=action.step_index + 1)}


def apply_choice_answer(state: GameFlowState) -> dict[str, Any]:
    """Sprint 08, WI3 -- fills the move ref an `ACCEPT_CHOICE` answered
    directly from the resumed answer text (`effect.payload["text"]`),
    rather than `operations._accept_choice`'s own `consumer_payload`
    lookup, which only helps a pre-resolved single-target confirmation,
    not an ambiguous-reference choice among several live options (←
    scenario 8): the option *is* the chosen id, decided only once the
    player answers."""
    effect = state["effect"]
    move = state["move"]
    if not isinstance(effect, Operation) or effect.kind != OperationKind.ACCEPT_CHOICE:
        return {}
    if move is None:
        return {}
    choice_key = effect.payload.get("ref_key")
    text = effect.payload.get("text")
    if not choice_key or not text or move.refs.get(choice_key):
        return {}
    return {"move": replace(move, refs={**move.refs, choice_key: text})}


def _expand_read_move_plan(
    hero_id: str, proposed: tuple[OperationSpec, ...]
) -> tuple[OperationSpec, ...]:
    """A `READ_MOVE` decision may only propose operations from its own
    `allowed_operations` (never a consumer or `COMPLETE_ACTION`, ←
    `decisions.py`'s own validation) -- this expands that one authored
    step into a full plan. A single `REQUEST_ROLL` step names its own
    consumer in `payload["consumer"]`, expanded through `player_roll_plan`
    exactly as an authored check would be; anything else is a plain
    mutation, closed off with `COMPLETE_ACTION`."""
    if len(proposed) == 1 and proposed[0].kind is OperationKind.REQUEST_ROLL:
        payload = proposed[0].payload
        return player_roll_plan(
            actor_id=payload.get("actor_id", hero_id),
            consumer=OperationKind(payload["consumer"]),
            payload=payload,
        )
    return (*proposed, OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}))


def apply_decision(
    state: GameFlowState, situation: Situation, result: DecisionResult
) -> dict[str, Any]:
    """Sprint 08, WI3 -- reconciles one `decide()` result into `move`/
    `action` (or, for an ambiguous reference, straight into the next
    `effect`), called by `flow_nodes.advance()` right after a `decide()`
    visit. Nothing in the sprint 011/05-07 modules previously consumed a
    `DecisionResult` at all -- `advance_action` would have looped
    forever re-requesting `READ_MOVE` once `state["move"]` never left
    `None` (← bug, blocks every scenario)."""
    hero_id = situation.hero.id

    if result.kind is DecisionKind.READ_MOVE:
        decision: ReadMoveDecision = result.value
        move = Move(intent=decision.intent, refs=dict(decision.refs))
        delta: dict[str, Any] = {"move": move}
        if decision.proposed:
            delta["action"] = ActionCursor(
                action_id=_new_id(),
                actor_id=hero_id,
                kind=decision.intent,
                plan=_expand_read_move_plan(hero_id, decision.proposed),
                step_index=0,
                status="planned",
                roll_id=None,
                roll_consumed=False,
            )
        elif decision.intent != "attack":
            # No mechanical plan -- a pure narrative move (talk, look, a
            # rules question already answered by `READ_MOVE`'s own tool
            # loop). Marking the action already "complete" with an empty
            # plan lets `advance_narration` draft the answer beat next,
            # without a second decision call this scheduler does not need
            # (the mechanic diagrams' extra `decide` step is not required
            # -- ← brief, "never node sequences").
            delta["action"] = ActionCursor(
                action_id=_new_id(),
                actor_id=hero_id,
                kind=decision.intent,
                plan=(),
                step_index=0,
                status="complete",
                roll_id=None,
                roll_consumed=False,
            )
        # `intent == "attack"` with no plan: `action` stays `None` so
        # `advance_action` defers to `advance_combat`'s own scheduling
        # (initiative first, the hero's own plan only once it is the
        # hero's turn -- `flow_nodes.materialize_hero_action`).
        return delta

    if result.kind is DecisionKind.JUDGE_REFERENCE:
        judgement: ReferenceJudgement = result.value
        move = state["move"]
        if judgement.chosen_id is not None and move is not None:
            return {"move": replace(move, refs={**move.refs, "target_id": judgement.chosen_id})}
        if judgement.ask_choice:
            return {
                "effect": Operation(
                    operation_id=_new_id(),
                    kind=OperationKind.REQUEST_CHOICE,
                    payload={
                        "actor_id": hero_id,
                        "text": "Which one do you mean?",
                        "options": list(judgement.ask_choice),
                        "consumer": OperationKind.ACCEPT_CHOICE.value,
                        "consumer_payload": {"ref_key": "target_id"},
                    },
                )
            }
        return {}

    if result.kind is DecisionKind.MONSTER_ACTION:
        monster_action: MonsterAction = result.value
        return {
            "action": ActionCursor(
                action_id=_new_id(),
                actor_id=monster_action.actor_id,
                kind="attack",
                plan=attack_plan(
                    actor_id=monster_action.actor_id,
                    target_id=monster_action.target_id,
                    attack=monster_action.attack,
                    is_player=False,
                ),
                step_index=0,
                status="planned",
                roll_id=None,
                roll_consumed=False,
            )
        }

    return {}


def progress_combat(state: GameFlowState, situation: Situation) -> dict[str, Any]:
    """Sprint 08, WI3 -- advances `CombatCursor.index` past the actor
    whose `ActionCursor` just reached `"complete"`, so `eligible_hostiles`
    stops re-offering an actor who already acted this round and
    `flow_nodes.materialize_hero_action` stops re-building the hero's own
    plan. Nothing previously moved this cursor at all (← bug)."""
    combat = state["combat"]
    action = state["action"]
    if combat is None or action is None or action.status != "complete":
        return {}
    if combat.index >= len(combat.order) or combat.order[combat.index] != action.actor_id:
        return {}
    return {"combat": replace(combat, index=combat.index + 1)}


def materialize_hero_action(state: GameFlowState, situation: Situation) -> dict[str, Any]:
    """Sprint 08, WI3 -- once initiative has settled and the combat cursor
    reaches the hero's own slot, builds the hero's attack plan directly
    (no further decision -- the hero already declared "attack `target_id`"
    through `move`). Nothing previously scheduled the hero's own turn in
    combat at all; `advance_combat` only ever drives the hostile side."""
    combat = state["combat"]
    move = state["move"]
    action = state["action"]
    if combat is None or move is None or action is not None:
        return {}
    if move.intent != "attack":
        return {}
    if combat.index >= len(combat.order) or combat.order[combat.index] != situation.hero.id:
        return {}
    target_id = move.refs.get("target_id")
    if not target_id:
        return {}
    return {
        "action": ActionCursor(
            action_id=_new_id(),
            actor_id=situation.hero.id,
            kind="attack",
            plan=attack_plan(
                actor_id=situation.hero.id,
                target_id=target_id,
                attack=move.refs.get("attack", "attack"),
                is_player=True,
                item_id=move.refs.get("item_id"),
            ),
            step_index=0,
            status="planned",
            roll_id=None,
            roll_consumed=False,
        )
    }


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
    action = state["action"]
    # ← bug (sprint 08, WI3): this used to read `actor_id`/`target_id`
    # off `state["move"]` -- always the *hero's own* declared move, never
    # updated per monster turn, so a hostile's own hit was misattributed
    # to the hero (`is_player` always true) and its damage rolled against
    # the hero's own weapon instead of the attacker's. `action.actor_id`
    # and the plan's own `RESOLVE_ATTACK` step (index 1, both player and
    # monster) are the one place the *actual* attacker and target survive
    # past the roll -- `attack_plan`'s own contract.
    resolve_step = action.plan[1].payload if action is not None and len(action.plan) > 1 else {}
    actor_id = action.actor_id if action is not None else situation.hero.id
    target_id = resolve_step.get("target_id")
    is_player = actor_id == situation.hero.id
    has_damage_roll = action is not None and action.roll_id is not None and not action.roll_consumed
    # `derive_formula`'s `context["attack"]`/`context["item_id"]` (needed
    # once more than one attack is available, or for a character actor
    # at all) come from the same `RESOLVE_ATTACK` step, not `state["move"]`.
    attack_name = resolve_step.get("attack")
    item_id = resolve_step.get("item_id")
    if not has_damage_roll:
        # ← bug (sprint 08, WI3): `REQUEST_ROLL`/`request_player_roll`
        # refuses `kind="damage"` outright, same as the attack roll above
        # -- both sides roll damage through `ROLL_ACTOR`.
        return Operation(
            operation_id=_new_id(),
            kind=OperationKind.ROLL_ACTOR,
            payload={
                "actor_id": actor_id,
                "kind": "damage",
                "context": {"attack": attack_name, "item_id": item_id},
                "visibility": "player" if is_player else "dm",
            },
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
        if state["turn"].status in ("closed", "terminal"):
            # ← bug (sprint 08, WI3): `close_turn_state` (`flow_state.py`)
            # always clears `move`/`action`, even though the turn itself is
            # now closed -- without this guard `advance_action` mistook
            # every closed turn's next visit for the start of a fresh one
            # and re-requested `READ_MOVE`, looping forever instead of
            # letting `validate_turn_close`'s own final fallback report
            # `TurnComplete`.
            return None
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
        if move.intent == "attack" and not move.refs.get("target_id"):
            # An attack move with no bound target -- one or more live
            # candidates were ambiguous (scenario 8); `decide()`'s
            # `JUDGE_REFERENCE` either picks one on its own or asks.
            return DecisionRequest(
                decision_id=_new_id(),
                kind=DecisionKind.JUDGE_REFERENCE,
                evidence_ids=(),
                payload={"actor_id": situation.hero.id},
            )
        # A move is read but no plan has been reserved into an ActionCursor
        # yet -- building that cursor from the decision's proposed plan is
        # the `decide`/`execute` pipeline's own job (flow_nodes, WI2), not
        # an obligation this scheduler itself must resolve. An `"attack"`
        # move with a bound target and no cursor defers to
        # `advance_combat`'s own initiative scheduling, then to
        # `flow_nodes.materialize_hero_action` once it is the hero's turn.
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
    payload = step.payload
    if step.kind is OperationKind.RESOLVE_ATTACK and "roll_id" not in payload and action.roll_id:
        # `attack_plan`'s own `RESOLVE_ATTACK` step never carries a
        # `roll_id` -- unlike `RESOLVE_CHECK`/`RESOLVE_SAVE`
        # (`operations._resolve_roll`'s own fallback), `_resolve_attack`
        # requires one outright.
        payload = {**payload, "roll_id": action.roll_id}
    return Operation(operation_id=_new_id(), kind=step.kind, payload=payload)


def advance_combat(state: GameFlowState, situation: Situation) -> NextEffect | None:
    combat = state["combat"]
    move = state["move"]
    hostiles = eligible_hostiles(situation, combat)

    if combat is None:
        if not (hostiles and move is not None and move.intent == "attack"):
            return None
        effect = state["effect"]
        result = state["result"]
        if (
            isinstance(effect, Operation)
            and effect.kind is OperationKind.ROLL_PLAYER
            and isinstance(result, OperationResult)
            and result.status == "ok"
            and "roll_id" in result.value
        ):
            # The hero-side initiative roll just resolved (← `advance()`'s
            # `AwaitingRef(consumer=SETTLE_INITIATIVE)`, set by
            # `operations._settle_initiative`'s own "awaiting hero roll"
            # branch) -- settle with it now, instead of asking again.
            return Operation(
                operation_id=_new_id(),
                kind=OperationKind.SETTLE_INITIATIVE,
                payload={
                    "scene_id": situation.scene_id,
                    "hero_ids": [situation.hero.id],
                    "hostile_ids": list(hostiles),
                    "hero_roll_id": result.value["roll_id"],
                },
            )
        return Operation(
            operation_id=_new_id(),
            kind=OperationKind.SETTLE_INITIATIVE,
            payload={
                "scene_id": situation.scene_id,
                "hero_ids": [situation.hero.id],
                "hostile_ids": list(hostiles),
            },
        )

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
