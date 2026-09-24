"""Sprint 011/05, WI3 -- world/lifecycle handlers dispatch to the
monkeypatched service with the contracted kwargs, and the roll-ownership
rule (← AC4) is exercised at the state level."""

import asyncio
from dataclasses import dataclass
from typing import Any

from app.modules.game.agent.flow_state import (
    ActionCursor,
    NarrativeCursor,
    Operation,
    OperationKind,
    TurnFrame,
)
from app.modules.game.agent.operations_world import WORLD_HANDLERS, roll_available
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.schemas import MutationResult


@dataclass
class _Ctx:
    db: Any
    user_id: str
    run_id: str
    hero_id: str
    situation: Any


def _turn_frame() -> TurnFrame:
    return TurnFrame(
        run_id="run-1",
        hero_id="hero-1",
        turn_id="turn-1",
        input_kind="action",
        text="I take the sword",
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


def test_take_item_dispatches_to_the_service_and_returns_ok(monkeypatch):
    calls: dict[str, Any] = {}

    async def fake_take(db, *, user_id, actor_id, item_id, turn_id):
        calls["kwargs"] = {
            "db": db,
            "user_id": user_id,
            "actor_id": actor_id,
            "item_id": item_id,
            "turn_id": turn_id,
        }
        return MutationResult(status="ok", event_ids=["event-1"], facts={"itemId": item_id})

    monkeypatch.setattr(playthrough_service, "take", fake_take)

    ctx = _Ctx(db="db-handle", user_id="user-1", run_id="run-1", hero_id="hero-1", situation=None)
    op = Operation(
        operation_id="op-1",
        kind=OperationKind.TAKE_ITEM,
        payload={"actor_id": "hero-1", "item_id": "item-1"},
    )

    result, delta = asyncio.run(WORLD_HANDLERS[OperationKind.TAKE_ITEM](ctx, op, _state()))

    assert calls["kwargs"] == {
        "db": "db-handle",
        "user_id": "user-1",
        "actor_id": "hero-1",
        "item_id": "item-1",
        "turn_id": "turn-1",
    }
    assert result.operation_id == "op-1"
    assert result.status == "ok"
    assert result.event_ids == ("event-1",)
    assert delta == {}


def test_roll_available_is_true_when_no_roll_has_been_spent():
    action = ActionCursor(
        action_id="action-1",
        actor_id="hero-1",
        kind="attack",
        plan=(),
        step_index=0,
        status="reserved",
        roll_id="roll-1",
        roll_consumed=False,
    )

    assert roll_available(action) is True


def test_roll_available_refuses_once_the_action_s_roll_is_consumed():
    action = ActionCursor(
        action_id="action-1",
        actor_id="hero-1",
        kind="attack",
        plan=(),
        step_index=0,
        status="reserved",
        roll_id="roll-1",
        roll_consumed=True,
    )

    assert roll_available(action) is False
