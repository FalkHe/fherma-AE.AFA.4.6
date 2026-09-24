"""Sprint 011/06, WI1 -- `decide()` rejects a proposal the situation does
not recognise, re-prompts under the same `decision_id`, and gives up after
`RETRY_BUDGET`; the read-only tool loop stops at `MAX_TOOL_CALLS` total
calls (AC1, AC2)."""

import asyncio

import pytest
from langchain_core.messages import AIMessage

from app.modules.game.agent.decisions import (
    DecisionContext,
    DecisionInvalid,
    DecisionKind,
    DecisionRequest,
    MonsterActionOut,
    ReadMoveOut,
    decide,
)
from app.modules.game.agent.flow_state import NarrativeCursor, TurnFrame
from app.modules.playthrough.situation import ActorView, AttackView, Situation
from app.modules.srd import service as srd_service
from tests.game.fakes import ScriptedChatModel


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


def _monster() -> ActorView:
    return ActorView(
        id="goblin-1",
        name="Goblin",
        role="hostile",
        kind="monster",
        current_hp=7,
        max_hp=7,
        armour_class=13,
        is_alive=True,
        down=False,
        disposition=None,
        hostile=True,
        attacks=(AttackView(name="Scimitar", to_hit=4, damage="1d6+2"),),
        inventory=(),
    )


def _situation() -> Situation:
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
        hero=_hero(),
        actors=(_hero(), _monster()),
        fixtures=(),
        loose_items=(),
        exits=(),
        recent=(),
    )


def _ctx(model: ScriptedChatModel) -> DecisionContext:
    return DecisionContext(
        db="db-handle",
        user_id="user-1",
        run_id="run-1",
        hero_id="hero-1",
        situation=_situation(),
        model=model,
    )


def test_read_move_rejects_a_disallowed_operation_kind_and_raises_after_budget():
    """AC1: an operation kind outside the strategy's allowed set is a
    validation failure, re-prompted under the same `decision_id`, and the
    decision raises once the retry budget is spent."""
    bad = ReadMoveOut(
        intent="close the vault",
        refs={},
        proposed=[{"kind": "close_turn", "payload": {}}],
    )
    script = []
    for _ in range(3):  # RETRY_BUDGET + 1 attempts
        script.append(AIMessage(content="no tools needed"))  # tool-loop turn (no tool_calls)
        script.append(bad)  # structured answer, still invalid
    model = ScriptedChatModel(script)
    ctx = _ctx(model)
    request = DecisionRequest(
        decision_id="d-1",
        kind=DecisionKind.READ_MOVE,
        evidence_ids=(),
        payload={"text": "close it"},
    )

    with pytest.raises(DecisionInvalid):
        asyncio.run(decide(ctx, request, _state()))

    assert model.script == []


def test_monster_action_rejects_a_target_not_in_the_situation():
    """AC1: `target_id` naming a creature the situation does not know is a
    stale reference, rejected the same way as an unknown operation kind."""
    bad = MonsterActionOut(actor_id="goblin-1", attack="Scimitar", target_id="not-present")
    script = [bad for _ in range(3)]  # RETRY_BUDGET + 1 attempts, no tool loop for this strategy
    model = ScriptedChatModel(script)
    ctx = _ctx(model)
    request = DecisionRequest(
        decision_id="d-2", kind=DecisionKind.MONSTER_ACTION, evidence_ids=(), payload={}
    )

    with pytest.raises(DecisionInvalid):
        asyncio.run(decide(ctx, request, _state()))

    assert model.script == []


def test_tool_loop_stops_at_three_calls_then_answers(monkeypatch):
    """AC2: with four scripted tool-call replies, the loop runs only
    `MAX_TOOL_CALLS` (3) of them before moving on to the structured
    answer -- the fourth is never consumed."""

    async def _fake_search_rules(db, *, query, limit=5):
        return []

    monkeypatch.setattr(srd_service, "search_rules", _fake_search_rules)

    tool_call = lambda i: AIMessage(  # noqa: E731
        content="",
        tool_calls=[{"name": "lookup_rule", "args": {"query": "grapple"}, "id": f"call-{i}"}],
    )
    good = ReadMoveOut(intent="grapple the goblin", refs={"target_id": "goblin-1"}, proposed=None)
    # Four tool-call replies are scripted; the loop only ever executes
    # three of them (`MAX_TOOL_CALLS`), so it asks for the structured
    # answer next, leaving the fourth tool-call reply unconsumed.
    script = [tool_call(1), tool_call(2), tool_call(3), good, tool_call(4)]
    model = ScriptedChatModel(script)
    ctx = _ctx(model)
    request = DecisionRequest(
        decision_id="d-3",
        kind=DecisionKind.READ_MOVE,
        evidence_ids=(),
        payload={"text": "grapple it"},
    )

    result = asyncio.run(decide(ctx, request, _state()))

    assert result.value.intent == "grapple the goblin"
    # exactly the fourth tool-call reply was left unconsumed
    assert model.script == [script[4]]
