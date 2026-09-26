"""Sprint 011/05, WI2 -- the combined operation registry is complete and
`execute_operation` refuses a stale reference before any service call.

Sprint 08 round 1 defect A adds `REQUIRED_KEYS` coverage: a payload missing
a key its own handler reads unconditionally (← live bug, run
01M36TZ745VSMGZP36YCT491CE: `interact` with no `object_id` reached
`_interact` and raised `KeyError`) is refused before dispatch, never
raised."""

import asyncio

import pytest

from app.modules.game.agent.flow_state import (
    NarrativeCursor,
    Operation,
    OperationKind,
    TurnFrame,
)
from app.modules.game.agent.operations import (
    OPERATION_HANDLERS,
    REQUIRED_KEYS,
    OperationContext,
    execute_operation,
)
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.situation import ActorView, Situation


def test_every_operation_kind_has_exactly_one_handler_and_no_extras():
    registered = set(OPERATION_HANDLERS.keys())
    all_kinds = set(OperationKind)

    assert registered == all_kinds
    assert len(OPERATION_HANDLERS) == len(OperationKind)


@pytest.mark.parametrize("kind", list(OperationKind))
def test_every_operation_kind_has_a_required_keys_entry(kind):
    assert kind in REQUIRED_KEYS


def _turn_frame() -> TurnFrame:
    return TurnFrame(
        run_id="run-1",
        hero_id="hero-1",
        turn_id="turn-1",
        input_kind="action",
        text="I attack the ghost",
        status="open",
        round_admitted=True,
    )


def _state() -> dict:
    return {
        "turn": _turn_frame(),
        "move": None,
        "action": None,
        "combat": None,
        "awaiting": None,
        "pending_hit_id": None,
        "pending_critical": False,
        "reactions": [],
        "narrative": NarrativeCursor(beat_id=None, draft=None, event_id=None),
        "effect": None,
        "result": None,
        "usage": None,
        "error": None,
    }


def _hero() -> ActorView:
    return ActorView(
        id="hero-1",
        name="Hero",
        role="hero",
        kind="player",
        current_hp=10,
        max_hp=10,
        armour_class=15,
        is_alive=True,
        down=False,
        disposition=None,
        hostile=False,
        attacks=(),
        inventory=(),
    )


def _situation() -> Situation:
    hero = _hero()
    return Situation(
        run_id="run-1",
        hero_id="hero-1",
        adventure_run_id="adv-1",
        scene_id="scene-1",
        campaign_title="Campaign",
        adventure_title="Adventure",
        scene_title="Scene",
        truth=(),
        consequences=(),
        pressure=None,
        npc_intent=None,
        secrets=(),
        hero=hero,
        actors=(hero,),
        fixtures=(),
        loose_items=(),
        exits=(),
        recent=(),
    )


def test_execute_operation_refuses_a_stale_actor_reference_without_a_service_call(monkeypatch):
    called = False

    async def fake_take(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(playthrough_service, "take", fake_take)

    ctx = OperationContext(
        db="db-handle", user_id="user-1", run_id="run-1", hero_id="hero-1", situation=_situation()
    )
    op = Operation(
        operation_id="op-1",
        kind=OperationKind.TAKE_ITEM,
        payload={"actor_id": "ghost-not-present", "item_id": "item-1"},
    )

    result, delta = asyncio.run(execute_operation(ctx, op, _state()))

    assert result.status == "refused"
    assert result.reason == "stale_reference"
    assert delta == {}
    assert called is False


def test_execute_operation_refuses_interact_missing_object_id_without_a_service_call(
    monkeypatch,
):
    """← live bug, run 01M36TZ745VSMGZP36YCT491CE: the model proposed an
    `interact` naming only `actor_id`/`action`, no `object_id`. Previously
    this reached `playthrough_service.interact` and raised `KeyError`;
    now it is refused before any service call."""
    called = False

    async def fake_interact(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(playthrough_service, "interact", fake_interact)

    ctx = OperationContext(
        db="db-handle", user_id="user-1", run_id="run-1", hero_id="hero-1", situation=_situation()
    )
    op = Operation(
        operation_id="op-1",
        kind=OperationKind.INTERACT,
        payload={"actor_id": "hero-1", "action": "ask about the shepherd"},
    )

    result, delta = asyncio.run(execute_operation(ctx, op, _state()))

    assert result.status == "refused"
    assert result.reason == "missing_key:object_id"
    assert delta == {}
    assert called is False


def test_execute_operation_refuses_give_item_with_a_stale_receiver(monkeypatch):
    called = False

    async def fake_give(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(playthrough_service, "give", fake_give)

    ctx = OperationContext(
        db="db-handle", user_id="user-1", run_id="run-1", hero_id="hero-1", situation=_situation()
    )
    op = Operation(
        operation_id="op-1",
        kind=OperationKind.GIVE_ITEM,
        payload={"from_id": "hero-1", "to_id": "ghost-not-present", "item_id": "item-1"},
    )

    result, delta = asyncio.run(execute_operation(ctx, op, _state()))

    assert result.status == "refused"
    assert result.reason == "stale_reference"
    assert delta == {}
    assert called is False


def test_roll_actor_refuses_instead_of_crashing_when_derivation_raises(monkeypatch):
    """← live bug (run 01M3E8VSFCZ856D2SNFATQXAPM): `playthrough_service.roll`
    raising `ValueError` (a weaponless actor, or an unresolved attack name)
    used to propagate straight out of `_roll_actor` and 500 the whole
    turn. It must refuse the step instead, exactly like a stale reference
    or a missing key."""

    async def fake_roll(*args, **kwargs):
        raise ValueError("this actor has no attacks")

    monkeypatch.setattr(playthrough_service, "roll", fake_roll)

    ctx = OperationContext(
        db="db-handle", user_id="user-1", run_id="run-1", hero_id="hero-1", situation=_situation()
    )
    op = Operation(
        operation_id="op-1",
        kind=OperationKind.ROLL_ACTOR,
        payload={"actor_id": "hero-1", "kind": "attack", "context": {"item_id": "shield-1"}},
    )

    result, delta = asyncio.run(execute_operation(ctx, op, _state()))

    assert result.status == "refused"
    assert result.reason == "this actor has no attacks"
    assert delta == {}


def test_resolve_attack_records_critical_on_the_state_delta(monkeypatch):
    """← finding (run 01M3E8VSFCZ856D2SNFATQXAPM): a natural-20 hit's own
    `critical` status never reached the later `damage` step because
    nothing on the flow state remembered it. `_resolve_attack` must set
    `pending_critical` alongside `pending_hit_id` so `advance_hit` can
    still tell a crit from a plain hit once the roll is spent."""
    from app.modules.playthrough.schemas import AttackResult

    async def fake_attack(*args, **kwargs):
        return AttackResult(
            status="critical", hit_id="hit-1", total=24, natural=20, armour_class=14
        )

    monkeypatch.setattr(playthrough_service, "attack", fake_attack)

    ctx = OperationContext(
        db="db-handle", user_id="user-1", run_id="run-1", hero_id="hero-1", situation=_situation()
    )
    op = Operation(
        operation_id="op-1",
        kind=OperationKind.RESOLVE_ATTACK,
        payload={"actor_id": "hero-1", "target_id": "hero-1", "roll_id": "roll-1"},
    )

    result, delta = asyncio.run(execute_operation(ctx, op, _state()))

    assert result.status == "ok"
    assert delta["pending_hit_id"] == "hit-1"
    assert delta["pending_critical"] is True


def test_resolve_attack_clears_critical_on_a_plain_hit(monkeypatch):
    from app.modules.playthrough.schemas import AttackResult

    async def fake_attack(*args, **kwargs):
        return AttackResult(status="hit", hit_id="hit-1", total=17, natural=13, armour_class=14)

    monkeypatch.setattr(playthrough_service, "attack", fake_attack)

    ctx = OperationContext(
        db="db-handle", user_id="user-1", run_id="run-1", hero_id="hero-1", situation=_situation()
    )
    op = Operation(
        operation_id="op-1",
        kind=OperationKind.RESOLVE_ATTACK,
        payload={"actor_id": "hero-1", "target_id": "hero-1", "roll_id": "roll-1"},
    )

    result, delta = asyncio.run(execute_operation(ctx, op, _state()))

    assert result.status == "ok"
    assert delta["pending_critical"] is False
