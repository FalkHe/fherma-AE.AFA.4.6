"""Operation dispatch for the new flow (sprint 011/05, WI2): player-input,
check and combat handlers, reference validation, and the combined registry
that merges them with `operations_world.WORLD_HANDLERS`.

Every handler is thin -- a single `playthrough_service` call plus the
`StateDelta` the graph applies -- and owns no transaction of its own; the
service call it wraps commits, exactly as `agent/tools.py` already relies
on for the old graph.
"""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.situation import Situation

from .flow_state import (
    AwaitingRef,
    CombatCursor,
    GameFlowState,
    Operation,
    OperationKind,
    OperationResult,
    StateDelta,
)
from .operations_world import WORLD_HANDLERS


@dataclass(frozen=True)
class OperationContext:
    db: AsyncSession
    user_id: str
    run_id: str
    hero_id: str
    situation: Situation


Handler = Callable[
    [OperationContext, Operation, GameFlowState], Awaitable[tuple[OperationResult, StateDelta]]
]


def _ok(
    op: Operation, *, event_ids: tuple[str, ...] = (), value: dict[str, Any] | None = None
) -> OperationResult:
    return OperationResult(
        operation_id=op.operation_id,
        status="ok",
        reason=None,
        event_ids=event_ids,
        value=value or {},
    )


def _refused(op: Operation, reason: str) -> OperationResult:
    return OperationResult(
        operation_id=op.operation_id, status="refused", reason=reason, event_ids=(), value={}
    )


REQUIRED_KEYS: dict[OperationKind, tuple[str, ...]] = {
    # ← live bug (run 01M36TZ745VSMGZP36YCT491CE): the model proposed an
    # `interact` with no `object_id`; `validate_refs` only checks a key
    # when present, so the payload reached `_interact`
    # (`operations_world.py`) and raised `KeyError` inside the execute
    # node. Every key a handler below reads with `payload[...]` (never
    # `.get`) is named here -- `execute_operation` refuses a payload
    # missing one before any handler ever runs, so a handler can no
    # longer `KeyError` on a model-shaped payload.
    OperationKind.RECORD_BEAT: (),
    OperationKind.COMPLETE_ACTION: (),
    OperationKind.CLOSE_TURN: (),
    OperationKind.FINISH_RUN: ("outcome",),
    OperationKind.REQUEST_ROLL: ("actor_id", "ability", "consumer"),
    OperationKind.ROLL_PLAYER: (),
    OperationKind.REQUEST_CHOICE: ("text", "options", "consumer"),
    OperationKind.ACCEPT_CHOICE: ("text",),
    OperationKind.ROLL_ACTOR: ("actor_id", "kind"),
    OperationKind.PASSIVE_CHECK: ("actor_id", "ability", "dc"),
    OperationKind.RESOLVE_CHECK: ("dc",),
    OperationKind.RESOLVE_SAVE: ("dc",),
    OperationKind.SETTLE_INITIATIVE: ("hero_ids", "hostile_ids", "scene_id"),
    OperationKind.INTERACT: ("actor_id", "object_id", "action"),
    OperationKind.TAKE_ITEM: ("actor_id", "item_id"),
    OperationKind.DROP_ITEM: ("actor_id", "item_id"),
    OperationKind.GIVE_ITEM: ("from_id", "to_id", "item_id"),
    OperationKind.USE_EXIT: ("actor_id", "exit_id"),
    OperationKind.ENTER_NEXT_ADVENTURE: (),
    OperationKind.SET_HOSTILITY: ("actor_id", "hostile"),
    OperationKind.LEAVE_SCENE: ("actor_id",),
    OperationKind.RESOLVE_ATTACK: ("actor_id", "target_id", "roll_id"),
    OperationKind.APPLY_DAMAGE: ("target_id", "roll_id"),
}


def missing_required_key(op: Operation) -> str | None:
    """The first key `REQUIRED_KEYS[op.kind]` names that `op.payload` does
    not carry, or `None`. Checked by `execute_operation` before
    `validate_refs`/dispatch -- a payload missing a key its own handler
    reads unconditionally must never reach that handler."""
    for key in REQUIRED_KEYS.get(op.kind, ()):
        if key not in op.payload:
            return key
    return None


def validate_refs(situation: Situation, op: Operation) -> str | None:
    """Checks every object id an operation's payload names against
    `situation`'s own present actors, fixtures, loose items, exits and
    hero/actor inventories, before any service call is made. Returns a
    refusal reason (`"stale_reference"`) or `None`. A key absent from the
    payload is never checked -- most operations only name a few of these."""
    payload = op.payload
    actor_ids = {actor.id for actor in situation.actors} | {situation.hero.id}
    fixture_ids = {fixture.id for fixture in situation.fixtures}
    exit_ids = {exit_.id for exit_ in situation.exits}
    inventory_ids = {item.id for item in situation.hero.inventory}
    for actor in situation.actors:
        inventory_ids |= {item.id for item in actor.inventory}
    loose_item_ids = {item.id for item in situation.loose_items}
    known_ids = actor_ids | fixture_ids | exit_ids | inventory_ids | loose_item_ids

    for key in ("actor_id", "target_id", "from_id", "to_id"):
        value = payload.get(key)
        if value is not None and value not in actor_ids:
            return "stale_reference"

    object_id = payload.get("object_id")
    if object_id is not None and object_id not in (fixture_ids | loose_item_ids | exit_ids):
        return "stale_reference"

    item_id = payload.get("item_id")
    if item_id is not None and item_id not in (loose_item_ids | inventory_ids):
        return "stale_reference"

    exit_id = payload.get("exit_id")
    if exit_id is not None and exit_id not in exit_ids:
        return "stale_reference"

    choice = payload.get("choice")
    if choice is not None and choice not in known_ids:
        return "stale_reference"

    attack = payload.get("attack")
    if attack is not None:
        actor_id = payload.get("actor_id")
        actor = next(
            (
                candidate
                for candidate in (*situation.actors, situation.hero)
                if candidate.id == actor_id
            ),
            None,
        )
        attack_names = {view.name for view in actor.attacks} if actor is not None else set()
        if attack not in attack_names:
            return "stale_reference"

    return None


async def _request_roll(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    context = {
        "ability": payload["ability"],
        "skill": payload.get("skill"),
        "dc": payload.get("dc"),
    }
    event = await playthrough_service.request_player_roll(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=payload["actor_id"],
        kind=payload.get("kind", "ability_check"),
        context=context,
        turn_id=state["turn"].turn_id,
    )
    awaiting = AwaitingRef(
        request_id=event.id,
        kind="roll",
        actor_id=payload["actor_id"],
        public=context,
        consumer=OperationKind(payload["consumer"]),
        consumer_payload=payload.get("consumer_payload", {}),
    )
    return _ok(op, event_ids=(event.id,)), {"awaiting": awaiting}


async def _roll_player(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    awaiting = state["awaiting"]
    assert awaiting is not None
    event = await playthrough_service.resolve_roll_request(
        ctx.db, user_id=ctx.user_id, request_id=awaiting.request_id, turn_id=state["turn"].turn_id
    )
    delta: StateDelta = {"awaiting": None}
    if state["action"] is not None:
        delta["action"] = replace(state["action"], roll_id=event.id, roll_consumed=False)
    return _ok(op, event_ids=(event.id,), value={"roll_id": event.id}), delta


async def _request_choice(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    event = await playthrough_service.ask_player(
        ctx.db,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        text=payload["text"],
        options=payload["options"],
        turn_id=state["turn"].turn_id,
    )
    awaiting = AwaitingRef(
        request_id=event.id,
        kind="choice",
        actor_id=payload.get("actor_id", ctx.hero_id),
        public={"text": payload["text"], "options": payload["options"]},
        consumer=OperationKind(payload["consumer"]),
        consumer_payload=payload.get("consumer_payload", {}),
    )
    return _ok(op, event_ids=(event.id,)), {"awaiting": awaiting}


async def _accept_choice(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    awaiting = state["awaiting"]
    assert awaiting is not None
    event = await playthrough_service.record_answer(
        ctx.db,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        text=payload["text"],
        question_id=awaiting.request_id,
        turn_id=state["turn"].turn_id,
    )
    delta: StateDelta = {"awaiting": None}
    # ← key renamed from `"choice"` (`advance.resume_operation`'s own
    # fix, sprint 08 WI3): `"choice"` collided with `validate_refs`'s own
    # `payload.get("choice")` check, which expects an *object* id there
    # for a different `Operation` shape entirely.
    choice_key = payload.get("ref_key")
    if choice_key is not None and state["move"] is not None:
        # `"choices"` (`advance.choice_options`'s own private label -> id
        # mapping, ← live bug round 3): the player's own answer echoes
        # one of `REQUEST_CHOICE`'s human-readable `options`, never an
        # id, so it is looked up here first. `consumer_payload.get(
        # choice_key)` is the older, single pre-resolved target shape
        # (`advance.apply_choice_answer`'s own docstring) -- still tried
        # as a fallback, never the other way around.
        choices = awaiting.consumer_payload.get("choices")
        object_id = choices.get(payload["text"]) if isinstance(choices, Mapping) else None
        if object_id is None:
            object_id = awaiting.consumer_payload.get(choice_key)
        if object_id is not None:
            delta["move"] = replace(
                state["move"], refs={**state["move"].refs, choice_key: object_id}
            )
    return _ok(op, event_ids=(event.id,)), delta


async def _roll_actor(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    try:
        event = await playthrough_service.roll(
            ctx.db,
            user_id=ctx.user_id,
            actor_id=payload["actor_id"],
            kind=payload["kind"],
            context=payload.get("context", {}),
            visibility=payload.get("visibility", "dm"),
            turn_id=state["turn"].turn_id,
        )
    except ValueError as exc:
        # ← live bug (run 01M3E8VSFCZ856D2SNFATQXAPM): `dice.derive_formula`
        # raising over a weapon-less actor or an unresolved attack name --
        # a modelling mistake `reconcile_step` already knows how to close
        # a plan out over (same as any other refused step) -- crashed the
        # whole turn with a 500 instead, since nothing here ever caught it.
        return _refused(op, str(exc)), {}
    delta: StateDelta = {}
    if state["action"] is not None:
        # ← bug (sprint 08, WI3): unlike `_roll_player`, this never wrote
        # the rolled event back onto `action.roll_id` -- a monster's own
        # `RESOLVE_ATTACK`/`APPLY_DAMAGE` plan step (`advance.advance_
        # action`'s own fallback, `advance.advance_hit`) then found no
        # roll to consume.
        delta["action"] = replace(state["action"], roll_id=event.id, roll_consumed=False)
    return _ok(op, event_ids=(event.id,), value={"roll_id": event.id}), delta


async def _passive_check(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    success = await playthrough_service.passive_check(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=payload["actor_id"],
        ability=payload["ability"],
        dc=payload["dc"],
        turn_id=state["turn"].turn_id,
        skill=payload.get("skill"),
    )
    return _ok(op, value={"success": success}), {}


async def _resolve_roll(
    ctx: OperationContext,
    op: Operation,
    state: GameFlowState,
    service_call: Callable[..., Awaitable[bool]],
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    action = state["action"]
    if action is not None and action.roll_consumed:
        return _refused(op, "roll_already_consumed"), {}
    roll_id = payload.get("roll_id") or (action.roll_id if action is not None else None)
    success = await service_call(
        ctx.db,
        user_id=ctx.user_id,
        roll_id=roll_id,
        dc=payload["dc"],
        turn_id=state["turn"].turn_id,
    )
    delta: StateDelta = {}
    if action is not None:
        delta["action"] = replace(action, roll_consumed=True)
    return _ok(op, value={"success": success}), delta


async def _resolve_check(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    return await _resolve_roll(ctx, op, state, playthrough_service.resolve_check)


async def _resolve_save(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    return await _resolve_roll(ctx, op, state, playthrough_service.resolve_save)


async def _settle_initiative(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    hero_roll_id = payload.get("hero_roll_id")
    if hero_roll_id is None:
        event = await playthrough_service.request_hero_initiative(
            ctx.db,
            user_id=ctx.user_id,
            hero_ids=list(payload["hero_ids"]),
            turn_id=state["turn"].turn_id,
        )
        # ← bug (sprint 08, WI3): without an `AwaitingRef` here, nothing
        # ever interrupted for the hero's own initiative roll --
        # `advance_request` never fires and `advance_combat` re-requests
        # the same roll forever. `advance.advance_combat` reads the
        # resolved roll id back off the resumed `ROLL_PLAYER`'s own
        # result once this request is answered.
        awaiting = AwaitingRef(
            request_id=event.id,
            kind="roll",
            actor_id=payload["hero_ids"][0],
            public={"ability": "initiative"},
            consumer=OperationKind.SETTLE_INITIATIVE,
            consumer_payload={
                "scene_id": payload["scene_id"],
                "hero_ids": list(payload["hero_ids"]),
                "hostile_ids": list(payload["hostile_ids"]),
            },
        )
        return _ok(op, event_ids=(event.id,), value={"status": "awaiting_hero_roll"}), {
            "awaiting": awaiting
        }
    result = await playthrough_service.settle_initiative(
        ctx.db,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        hero_roll_id=hero_roll_id,
        hero_ids=list(payload["hero_ids"]),
        hostile_ids=list(payload["hostile_ids"]),
        turn_id=state["turn"].turn_id,
    )
    combat = CombatCursor(
        scene_id=payload["scene_id"],
        order=tuple(result.order),
        index=0,
        round=1,
        round_admitted=True,
        winning_side=result.winning_side,
    )
    value = {"winning_side": result.winning_side, "order": tuple(result.order)}
    return _ok(op, event_ids=(result.hero_roll_id, result.hostile_roll_id), value=value), {
        "combat": combat
    }


async def _resolve_attack(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    result = await playthrough_service.attack(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=payload["actor_id"],
        target_id=payload["target_id"],
        item_id=payload.get("item_id"),
        roll_id=payload["roll_id"],
        turn_id=state["turn"].turn_id,
    )
    delta: StateDelta = {}
    action = state["action"]
    if action is not None:
        # ← bug (sprint 08, WI3): unlike `_resolve_roll` (`RESOLVE_CHECK`/
        # `RESOLVE_SAVE`), this never marked the attack roll consumed, so
        # `advance_hit`'s own `has_damage_roll` check mistook the spent
        # attack roll for an already-rolled damage roll and skipped
        # requesting one.
        delta["action"] = replace(action, roll_consumed=True)
    if result.status in ("hit", "critical"):
        delta["pending_hit_id"] = result.hit_id
    value = {
        "status": result.status,
        "total": result.total,
        "natural": result.natural,
        "armour_class": result.armour_class,
    }
    return _ok(op, value=value), delta


async def _apply_damage(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    payload = op.payload
    result = await playthrough_service.damage(
        ctx.db,
        user_id=ctx.user_id,
        target_id=payload["target_id"],
        roll_id=payload["roll_id"],
        hit_id=payload.get("hit_id") or state["pending_hit_id"],
        turn_id=state["turn"].turn_id,
        critical=payload.get("critical", False),
    )
    value = {
        "applied": result.applied,
        "current_hp": result.current_hp,
        "max_hp": result.max_hp,
        "is_alive": result.is_alive,
        "down": result.down,
    }
    return _ok(op, value=value), {"pending_hit_id": None}


_LOCAL_HANDLERS: dict[OperationKind, Handler] = {
    OperationKind.REQUEST_ROLL: _request_roll,
    OperationKind.ROLL_PLAYER: _roll_player,
    OperationKind.REQUEST_CHOICE: _request_choice,
    OperationKind.ACCEPT_CHOICE: _accept_choice,
    OperationKind.ROLL_ACTOR: _roll_actor,
    OperationKind.PASSIVE_CHECK: _passive_check,
    OperationKind.RESOLVE_CHECK: _resolve_check,
    OperationKind.RESOLVE_SAVE: _resolve_save,
    OperationKind.SETTLE_INITIATIVE: _settle_initiative,
    OperationKind.RESOLVE_ATTACK: _resolve_attack,
    OperationKind.APPLY_DAMAGE: _apply_damage,
}

OPERATION_HANDLERS: dict[OperationKind, Handler] = {**_LOCAL_HANDLERS, **WORLD_HANDLERS}


async def execute_operation(
    ctx: OperationContext, op: Operation, state: GameFlowState
) -> tuple[OperationResult, StateDelta]:
    """Validates `op`'s references against `ctx.situation` first -- a stale
    id reaches no service call, ever -- then dispatches through
    `OPERATION_HANDLERS`. An `op.kind` with no handler (should not happen
    once every `OperationKind` is registered) is an `"error"`, not a
    refusal: it is this module's own bug, not a bad reference."""
    missing = missing_required_key(op)
    if missing is not None:
        return _refused(op, f"missing_key:{missing}"), {}

    reason = validate_refs(ctx.situation, op)
    if reason is not None:
        return _refused(op, reason), {}

    handler = OPERATION_HANDLERS.get(op.kind)
    if handler is None:
        return (
            OperationResult(
                operation_id=op.operation_id,
                status="error",
                reason=f"no handler registered for {op.kind!r}",
                event_ids=(),
                value={},
            ),
            {},
        )
    return await handler(ctx, op, state)
