"""Sprint 011/05, WI2 -- the combined operation registry is complete and
`execute_operation` refuses a stale reference before any service call."""

import asyncio

from app.modules.game.agent.flow_state import (
    NarrativeCursor,
    Operation,
    OperationKind,
    TurnFrame,
)
from app.modules.game.agent.operations import (
    OPERATION_HANDLERS,
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
