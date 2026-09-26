"""`advance`'s pure scheduler (sprint 011/07, WI1) -- see `docs/general/
game-flow.v2.md`, "Scheduler priority". `select_next_effect` reads
`GameFlowState` and a fresh `Situation` and returns exactly one
`effects.NextEffect`; it never calls a model, rolls a die, interrupts or
writes to the database. The eight priorities are ordinary functions
(`advance_terminal` .. `validate_turn_close`), each `state, situation ->
NextEffect | None`, tried in order by `select_next_effect`; the first one
that returns non-`None` wins.

The `resume_operation(awaiting, resume)` helper turns a checkpointed
  `ResumeResult` (from `await_player`'s `interrupt()`) into the operation
  that consumes it, or `None` when the response answers a request other
  than the one checkpointed. The node calls this once per resume, before
  `select_next_effect` runs again with `state["awaiting"]` cleared.
"""

import re
import uuid
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.situation import Situation

from .decisions import (
    DecisionKind,
    DecisionRequest,
    DecisionResult,
    MonsterAction,
    MoveAssessment,
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
    OperationKind,
    OperationResult,
    OperationSpec,
)


def _new_id() -> str:
    return uuid.uuid4().hex


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


# `READ_MOVE`'s own `intent` is free text ("a short description of what
# the player is trying to do", never a fixed enum -- ← its own prompt), so
# a search-like move is recognised by keyword, not exact match (← live
# bug, round 2: the model's real replies read "search for tracks" or
# "investigate the ground", never the bare word "search" alone, so an
# exact-membership check never fired outside this file's own tests).
_SEARCH_KEYWORDS = ("search", "investigate", "examine", "inspect", "look for", "track")
_MOVEMENT_KEYWORDS = (
    "climb",
    "continue",
    "descend",
    "enter",
    "follow",
    "go",
    "head",
    "leave",
    "move",
    "pass through",
    "proceed",
    "return",
    "travel",
    "walk",
)


def _authored_exit_for_move(text: str | None, situation: Situation):
    """Return the uniquely matching authored exit for explicit movement."""
    if not text:
        return None
    lowered = text.casefold()
    path_action = "take" in lowered and any(
        word in lowered for word in ("path", "track", "route", "road", "trail")
    )
    if not path_action and not any(
        re.search(rf"\b{re.escape(keyword)}\b", lowered) for keyword in _MOVEMENT_KEYWORDS
    ):
        return None
    candidates = situation.exits
    if len(candidates) == 1:
        return candidates[0]
    matches = tuple(
        exit_
        for exit_ in candidates
        if any(
            value and value.casefold() in lowered
            for value in (exit_.id, exit_.to, exit_.description)
        )
    )
    return matches[0] if len(matches) == 1 else None


def needs_move_assessment(intent: str, refs: Mapping[str, str], situation: Situation) -> bool:
    """A `READ_MOVE` result needs `ASSESS_MOVE` (an authored-check pipeline
    visit) rather than an immediate answer beat when it names a
    search-like intent over a scene with hidden facts, or names a fixture
    that still carries an unachieved authored check (← live bug, sprint
    011/08: neither `ASSESS_MOVE` nor `INTERPRET_EVIDENCE` was ever
    scheduled, so a search over a scene's own secret narrated straight
    through with no roll)."""
    lowered = intent.casefold()
    if situation.secrets and any(keyword in lowered for keyword in _SEARCH_KEYWORDS):
        return True
    fixture_id = refs.get("object_id") or refs.get("fixture_id")
    if fixture_id:
        fixture = next((f for f in situation.fixtures if f.id == fixture_id), None)
        if fixture is not None and fixture.checks:
            return True
    return False


# Same free-text problem as `_SEARCH_KEYWORDS` (← live bug, round 3): the
# real model's `intent` read "attack the goblin with my spear", never the
# bare word "attack" `apply_decision`'s every combat check (here and in
# `advance_action`/`advance_combat`/`materialize_hero_action`) compares
# against, so the exact-equality check silently fell through to the pure-
# narrative branch and closed the turn with an attempt-flavoured beat and
# no mechanics at all -- no `judge_reference`, no initiative, no attack
# roll. Canonicalising `intent` once, right here, keeps every downstream
# `== "attack"` check unchanged.
_ATTACK_KEYWORDS = ("attack", "strike", "stab", "swing at", "shoot", "slash", "fight")


def _canonical_intent(intent: str, proposed: tuple[OperationSpec, ...] | None) -> str:
    """`decision.intent` normalised to the literal `"attack"` every combat
    check in this module compares against, when it reads as an attack and
    proposes no mechanical plan of its own (`READ_MOVE`'s own
    `allowed_operations` never includes an attack operation -- an attack
    move never has `proposed`)."""
    if proposed:
        return intent
    lowered = intent.casefold()
    if any(keyword in lowered for keyword in _ATTACK_KEYWORDS):
        return "attack"
    return intent


def _sanitized_refs(intent: str, refs: Mapping[str, str], situation: Situation) -> dict[str, str]:
    """Drops an attack move's own `target_id` when it names no actor
    actually present (← live bug: an invented id, or one belonging to a
    scene the hero has already left, would otherwise reach
    `attack_plan`'s own `RESOLVE_ATTACK` step and be refused there with no
    recovery -- dropping it here instead lets `advance_action`'s own
    `JUDGE_REFERENCE` request run exactly as it does for a never-named
    target)."""
    sanitized = dict(refs)
    if intent != "attack":
        return sanitized
    target_id = sanitized.get("target_id")
    if target_id is not None:
        known_ids = {actor.id for actor in situation.actors} | {situation.hero.id}
        if target_id not in known_ids:
            sanitized.pop("target_id", None)
    return sanitized


def _describe_candidate(situation: Situation, object_id: str) -> str:
    """A human-readable label for any id `judge_reference` may name (actor,
    fixture, loose item or exit -- its own prompt's own candidate kinds),
    falling back to the bare id for one this `Situation` no longer
    recognises."""
    for actor in (*situation.actors, situation.hero):
        if actor.id == object_id:
            return actor.name
    for fixture in situation.fixtures:
        if fixture.id == object_id:
            return fixture.name
    for item in situation.loose_items:
        if item.id == object_id:
            return item.name
    for exit_ in situation.exits:
        if exit_.id == object_id:
            return exit_.description
    return object_id


def choice_options(situation: Situation, ids: tuple[str, ...]) -> dict[str, str]:
    """A private label -> id mapping for `REQUEST_CHOICE`'s own `options`
    (← brief: "human-readable options mapped privately to ids"). Same-
    named candidates (three identical "Goblin Raider"s, ← live bug) are
    numbered in encounter order so every label stays unique and every
    label still round-trips through `operations._accept_choice`'s own
    lookup."""
    labels = [_describe_candidate(situation, object_id) for object_id in ids]
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    seen: dict[str, int] = {}
    options: dict[str, str] = {}
    for object_id, label in zip(ids, labels, strict=True):
        if counts[label] > 1:
            seen[label] = seen.get(label, 0) + 1
            label = f"{label} ({seen[label]})"
        options[label] = object_id
    return options


def _authored_check_entry(
    situation: Situation, assessment: MoveAssessment
) -> tuple[Any, str, str | None] | None:
    """The one authored entry (`SecretView`/`FixtureCheckView`) the model's
    `assessment` names, validated against `situation` again here (never
    trust an index/id surviving from an earlier `Situation` snapshot) --
    or `None` when it names nothing usable (including `dc_source ==
    "rules"`, refused for now, ← brief). Returns the entry itself, its
    prose to reveal on success, and, for a fixture check only, the
    fixture's own id (`None` for a secret)."""
    if not assessment.applies or assessment.dc_source != "authored":
        return None
    if assessment.secret_index is not None:
        if 0 <= assessment.secret_index < len(situation.secrets):
            secret = situation.secrets[assessment.secret_index]
            return secret, secret.fact, None
        return None
    if assessment.fixture_id is not None:
        fixture = next((f for f in situation.fixtures if f.id == assessment.fixture_id), None)
        if fixture is None:
            return None
        check = next((c for c in fixture.checks if c.action == assessment.check_action), None)
        if check is None:
            return None
        return check, check.success, fixture.id
    return None


def fixture_roll_plan(
    *, actor_id: str, fixture_id: str, action: str, ability: str, skill: str | None, dc: int
) -> tuple[OperationSpec, ...]:
    """Rolled fixture (← `docs/general/game-flow.v2.md`, "Action plans"):
    request roll → (wait/player-roll, off-plan) → `INTERACT` with the
    roll → complete action. `_interact`'s own consequence assessment is
    `playthrough_service.interact`'s job, not this scheduler's."""
    return (
        OperationSpec(
            kind=OperationKind.REQUEST_ROLL,
            payload={
                "actor_id": actor_id,
                "ability": ability,
                "skill": skill,
                "dc": dc,
                "kind": "ability_check",
                "consumer": OperationKind.INTERACT.value,
                "consumer_payload": {
                    "actor_id": actor_id,
                    "object_id": fixture_id,
                    "action": action,
                },
            },
        ),
        OperationSpec(
            kind=OperationKind.INTERACT,
            payload={"actor_id": actor_id, "object_id": fixture_id, "action": action},
        ),
        OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}),
    )


def attack_plan(
    *,
    actor_id: str,
    target_id: str,
    attack: str | None,
    is_player: bool,
    item_id: str | None = None,
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
    the cursor.

    ← live bug (run 01M36TZ745VSMGZP36YCT491CE): a model-proposed step
    that `execute_operation` refused (a missing/stale reference) used to
    match neither branch below, so `advance_action` kept re-issuing the
    very same refused step forever -- the turn could never close. A
    refused step now marks the action `"complete"` outright, same as a
    plain narrative move, so `advance_narration` drafts an ordinary
    outcome/answer beat over it and the turn ends cleanly instead of
    looping."""
    action = state["action"]
    effect = state["effect"]
    result = state["result"]
    if action is None or not isinstance(effect, Operation):
        return {}
    if not isinstance(result, OperationResult):
        return {}
    if action.step_index >= len(action.plan):
        return {}
    if action.plan[action.step_index].kind != effect.kind:
        return {}
    if result.status == "refused":
        return {"action": replace(action, status="complete")}
    if result.status != "ok":
        return {}
    return {"action": replace(action, step_index=action.step_index + 1)}


def capture_check_outcome(state: GameFlowState) -> dict[str, Any]:
    """`RESOLVE_CHECK`/`RESOLVE_SAVE`'s own `success` value is about to be
    overwritten in `state["result"]` by the plan's next step
    (`COMPLETE_ACTION`) before `advance_narration` ever gets to read it --
    called by `flow_nodes.advance()` on every visit, same as
    `reconcile_step`, to save it onto `state["check_outcome"]` while it is
    still the last thing that happened."""
    effect = state["effect"]
    result = state["result"]
    if not isinstance(effect, Operation) or effect.kind not in (
        OperationKind.RESOLVE_CHECK,
        OperationKind.RESOLVE_SAVE,
    ):
        return {}
    if not isinstance(result, OperationResult) or result.status != "ok":
        return {}
    return {"check_outcome": bool(result.value.get("success"))}


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


def _with_default_actor(hero_id: str, spec: OperationSpec) -> OperationSpec:
    """`READ_MOVE`'s own prompt only asks the model for ids the move
    clearly names -- the acting hero is never one of them (← live bug:
    the model proposed a valid `use_exit`/`take_item`/... naming only the
    object, no `actor_id`, and execution raised `KeyError` reaching for
    one). Every operation this decision may propose acts on the hero
    unless the model already named an actor itself."""
    if "actor_id" in spec.payload:
        return spec
    return OperationSpec(kind=spec.kind, payload={**spec.payload, "actor_id": hero_id})


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
        consumer = payload.get("consumer")
        if consumer is None:
            # Decision validation rejects this before normal execution. Keep
            # this boundary defensive as well: a malformed DecisionResult
            # must become an ordinary refused operation, never a raw KeyError
            # that aborts the whole turn.
            return (
                OperationSpec(
                    kind=OperationKind.REQUEST_ROLL,
                    payload={**payload, "actor_id": payload.get("actor_id", hero_id)},
                ),
                OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}),
            )
        return player_roll_plan(
            actor_id=payload.get("actor_id", hero_id),
            consumer=OperationKind(consumer),
            payload=payload,
        )
    defaulted = tuple(_with_default_actor(hero_id, spec) for spec in proposed)
    return (*defaulted, OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}))


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
        proposed = decision.proposed
        if proposed is None:
            authored_exit = _authored_exit_for_move(state["turn"].text, situation)
            if authored_exit is not None:
                proposed = (
                    OperationSpec(
                        kind=OperationKind.USE_EXIT,
                        payload={"actor_id": hero_id, "exit_id": authored_exit.id},
                    ),
                )
        intent = _canonical_intent(decision.intent, decision.proposed)
        refs = _sanitized_refs(intent, decision.refs, situation)
        move = Move(intent=intent, refs=refs)
        delta: dict[str, Any] = {"move": move}
        if proposed:
            delta["action"] = ActionCursor(
                action_id=_new_id(),
                actor_id=hero_id,
                kind=intent,
                plan=_expand_read_move_plan(hero_id, proposed),
                step_index=0,
                status="planned",
                roll_id=None,
                roll_consumed=False,
            )
        elif intent != "attack":
            # No mechanical plan proposed. A search-like move over a scene
            # with hidden facts, or a move naming a fixture that still
            # carries an unachieved authored check, first needs
            # `ASSESS_MOVE` (`status="assessing"`, `advance_action`'s own
            # next visit requests it) -- everything else is a pure
            # narrative move (talk, look, a rules question already
            # answered by `READ_MOVE`'s own tool loop), marked "complete"
            # right away so `advance_narration` drafts the answer beat
            # next, without a second decision call this scheduler does
            # not need (the mechanic diagrams' extra `decide` step is not
            # required -- ← brief, "never node sequences").
            status = "assessing" if needs_move_assessment(intent, refs, situation) else "complete"
            delta["action"] = ActionCursor(
                action_id=_new_id(),
                actor_id=hero_id,
                kind=intent,
                plan=(),
                step_index=0,
                status=status,
                roll_id=None,
                roll_consumed=False,
            )
        # `intent == "attack"` with no plan: `action` stays `None` so
        # `advance_action` defers to `advance_combat`'s own scheduling
        # (initiative first, the hero's own plan only once it is the
        # hero's turn -- `flow_nodes.materialize_hero_action`).
        return delta

    if result.kind is DecisionKind.ASSESS_MOVE:
        assessment: MoveAssessment = result.value
        action = state["action"]
        if action is None:
            return {}
        entry = _authored_check_entry(situation, assessment)
        if entry is None:
            # Does not apply, or the model named no authored entry (or
            # tried `dc_source="rules"`, refused for now) -- straight to
            # the answer beat, no roll.
            return {"action": replace(action, status="complete")}
        mechanics, fact_text, fixture_id = entry
        ability, skill, dc = playthrough_service.authored_check(mechanics)
        if fixture_id is not None:
            plan = fixture_roll_plan(
                actor_id=hero_id,
                fixture_id=fixture_id,
                action=assessment.check_action or "",
                ability=ability,
                skill=skill,
                dc=dc,
            )
        else:
            plan = player_roll_plan(
                actor_id=hero_id,
                consumer=OperationKind.RESOLVE_CHECK,
                payload={"ability": ability, "skill": skill, "dc": dc, "fact": fact_text},
            )
        return {"action": replace(action, plan=plan, step_index=0, status="planned")}

    if result.kind is DecisionKind.JUDGE_REFERENCE:
        judgement: ReferenceJudgement = result.value
        move = state["move"]
        if judgement.chosen_id is not None and move is not None:
            return {"move": replace(move, refs={**move.refs, "target_id": judgement.chosen_id})}
        if judgement.ask_choice:
            options = choice_options(situation, judgement.ask_choice)
            return {
                "effect": Operation(
                    operation_id=_new_id(),
                    kind=OperationKind.REQUEST_CHOICE,
                    payload={
                        "actor_id": hero_id,
                        "text": "Which one do you mean?",
                        "options": list(options.keys()),
                        "consumer": OperationKind.ACCEPT_CHOICE.value,
                        # `"choices"` is the private label -> id mapping
                        # `operations._accept_choice` resolves the
                        # player's own answer text against -- the player
                        # only ever sees `options`' own human-readable
                        # labels (← brief), never an id.
                        "consumer_payload": {"ref_key": "target_id", "choices": options},
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
    plan. Nothing previously moved this cursor at all (← bug).

    A hostile's own completed cursor is also cleared back to `None` here
    (← live bug, round 3: when the hero lost initiative, every one of the
    three hostiles that acted before her left its own completed
    `ActionCursor` sitting in `state["action"]` -- `materialize_hero_
    action`'s own `action is not None` guard then mistook it for an
    unfinished obligation forever, and the hero's own turn never
    materialized at all). The hero's own completed cursor is left alone:
    `advance_narration`'s final outcome beat still needs to read it."""
    combat = state["combat"]
    action = state["action"]
    if combat is None or action is None or action.status != "complete":
        return {}
    if combat.index >= len(combat.order) or combat.order[combat.index] != action.actor_id:
        return {}
    delta: dict[str, Any] = {"combat": replace(combat, index=combat.index + 1)}
    if action.actor_id != situation.hero.id:
        delta["action"] = None
    return delta


def _resolve_hero_weapon(situation: Situation, refs: Mapping[str, str]) -> str | None:
    """Defaults an attack's own `item_id` to a carried item matching the
    named `attack` word, or the hero's first carried item that actually
    has an attack, when `READ_MOVE` left it unset -- `dice.derive_formula`
    refuses a character's own attack roll outright with no `item_id` at
    all (← live bug: "attack the goblin with my spear" named no item in
    `evidence` at all, since the hero carries only a knife, so
    `READ_MOVE` correctly left `item_id` unset per its own "never invent
    an id" rule; the hero's own attack roll is never an interrupt
    (`attack_plan`'s own docstring) and crashed the whole turn instead of
    asking again).

    The last-resort fallback picks deterministically among items that
    have at least one attack, ordered by the carried item's own id (←
    live bug, run 01M3E8VSFCZ856D2SNFATQXAPM: the underlying inventory
    query carries no `ORDER BY` at all, so a bare `inventory[0]` could
    just as well land on a shield or a lantern -- neither has an attack
    to roll, and `dice._select_attack` raised `ValueError` uncaught,
    500ing the whole turn). Carrying nothing with an attack at all
    returns `None`, letting `_roll_actor`'s own `ValueError` guard refuse
    the roll cleanly instead of ever inventing a weapon that isn't
    there."""
    item_id = refs.get("item_id")
    if item_id is not None:
        return item_id
    inventory = situation.hero.inventory
    if not inventory:
        return None
    attack_name = (refs.get("attack") or "").casefold()
    if attack_name:
        for item in inventory:
            item_name = item.name.casefold()
            if attack_name in item_name or item_name in attack_name:
                return item.id
    armed = sorted((item for item in inventory if item.attacks), key=lambda item: item.id)
    return armed[0].id if armed else None


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
                # `None`, not a placeholder string, when the move named
                # no attack: `dice._select_attack` picks the hero's own
                # sole attack automatically with a bare weapon (← live
                # bug: the literal string `"attack"` used to reach
                # `_select_attack` as an unmatched *name*, refusing the
                # roll outright even with only one real attack to pick).
                attack=move.refs.get("attack"),
                is_player=True,
                item_id=_resolve_hero_weapon(situation, move.refs),
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


def _finish_run_evidence(state: GameFlowState) -> tuple[tuple[str, ...], dict[str, Any]]:
    """The `FINISH_RUN` operation's own recorded evidence -- its ending
    `system` event plus its `outcome` fact -- read straight off
    `state["result"]`, the one operation `advance_terminal` itself always
    runs immediately before ever requesting the closing beat (← live bug:
    the closing `BeatRequest` used to carry neither at all, `payload={}`
    and `allowed_evidence_ids=()`, so the narrator had nothing telling it
    the run had just ended and hallucinated the player's own last,
    unresolved action as still under way instead). Guarded on `"outcome"`
    surviving in `result.value` rather than trusted unconditionally, since
    a resumed/retried turn could in principle reach here with a stale
    `state["result"]` left over from something else."""
    result = state["result"]
    if isinstance(result, OperationResult) and "outcome" in result.value:
        return result.event_ids, {"outcome": result.value["outcome"]}
    return (), {}


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
        evidence_ids, payload = _finish_run_evidence(state)
        return BeatRequest(
            beat_id=_new_id(), kind="closing", allowed_evidence_ids=evidence_ids, payload=payload
        )
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
            # `JUDGE_REFERENCE` either picks one on its own or asks. ←
            # live bug: this payload used to carry only the hero's own
            # id, never the player's own text -- the model had nothing
            # naming *which* ambiguity ("the goblin" among three) to
            # resolve at all.
            return DecisionRequest(
                decision_id=_new_id(),
                kind=DecisionKind.JUDGE_REFERENCE,
                evidence_ids=(),
                payload={"actor_id": situation.hero.id, "text": state["turn"].text},
            )
        # A move is read but no plan has been reserved into an ActionCursor
        # yet -- building that cursor from the decision's proposed plan is
        # the `decide`/`execute` pipeline's own job (flow_nodes, WI2), not
        # an obligation this scheduler itself must resolve. An `"attack"`
        # move with a bound target and no cursor defers to
        # `advance_combat`'s own initiative scheduling, then to
        # `flow_nodes.materialize_hero_action` once it is the hero's turn.
        return None
    if action.status == "assessing":
        return DecisionRequest(
            decision_id=_new_id(),
            kind=DecisionKind.ASSESS_MOVE,
            evidence_ids=(),
            payload={
                "text": state["turn"].text,
                "intent": action.kind,
                "refs": dict(move.refs) if move is not None else {},
            },
        )
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
    if (
        step.kind in (OperationKind.RESOLVE_ATTACK, OperationKind.INTERACT)
        and "roll_id" not in payload
        and action.roll_id
    ):
        # `attack_plan`'s own `RESOLVE_ATTACK` step never carries a
        # `roll_id` -- unlike `RESOLVE_CHECK`/`RESOLVE_SAVE`
        # (`operations._resolve_roll`'s own fallback), `_resolve_attack`
        # requires one outright. `fixture_roll_plan`'s own `INTERACT` step
        # is the same shape: `playthrough_service.interact` takes an
        # optional `roll_id`, but a rolled fixture check must still pass
        # it on, never fall back to a no-roll bypass.
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


def _resolved_check_fact(action: ActionCursor) -> str | None:
    """The fact text an `ASSESS_MOVE`-built check plan (`apply_decision`)
    stashed on its own `REQUEST_ROLL` step's `consumer_payload` -- the
    plan survives past `step_index` advancing, exactly as `advance_hit`
    already reads `action.plan[1]` for an attack's own attacker/target."""
    if not action.plan:
        return None
    first = action.plan[0]
    if first.kind is not OperationKind.REQUEST_ROLL:
        return None
    fact = first.payload.get("consumer_payload", {}).get("fact")
    return fact if isinstance(fact, str) else None


def advance_narration(state: GameFlowState, situation: Situation) -> NextEffect | None:
    narrative = state["narrative"]
    if narrative.draft is not None:
        return Operation(operation_id=_new_id(), kind=OperationKind.RECORD_BEAT, payload={})
    action = state["action"]
    if action is not None and action.status == "complete" and narrative.event_id is None:
        payload: dict[str, Any] = {}
        fact = _resolved_check_fact(action)
        if fact is not None and state.get("check_outcome"):
            payload["discovered"] = fact
        return BeatRequest(
            beat_id=_new_id(), kind="outcome", allowed_evidence_ids=(), payload=payload
        )
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
