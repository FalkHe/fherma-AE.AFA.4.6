"""Sprint 011/07, WI2 -- one boundary test per `flow_nodes` node, plus the
interrupt/resume round trip through a throwaway two-node graph (AC4)."""

import asyncio

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.core.checkpointer import service as checkpointer_service
from app.modules.game.agent import flow_nodes
from app.modules.game.agent.decisions import DecisionKind, DecisionRequest, ReadMoveOut
from app.modules.game.agent.effects import PlayerWait, ResumeResult, TurnComplete
from app.modules.game.agent.flow_state import (
    ActionCursor,
    GameFlowState,
    NarrativeCursor,
    Operation,
    OperationKind,
    OperationSpec,
    TurnFrame,
)
from app.modules.game.agent.narration import BeatRequest
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.situation import ActorView, Situation
from tests.game.fakes import ScriptedChatModel


def _turn(**overrides) -> TurnFrame:
    base = dict(
        run_id="run-1",
        hero_id="hero-1",
        turn_id="turn-1",
        input_kind="action",
        text="I look around",
        status="open",
        round_admitted=True,
    )
    return TurnFrame(**{**base, **overrides})


def _state(**overrides) -> GameFlowState:
    base = dict(
        turn=_turn(),
        move=None,
        action=None,
        combat=None,
        awaiting=None,
        resume=None,
        pending_hit_id=None,
        reactions=[],
        narrative=NarrativeCursor(beat_id=None, draft=None, event_id=None),
        effect=None,
        result=None,
        usage=None,
        error=None,
    )
    return {**base, **overrides}  # type: ignore[return-value]


def _hero() -> ActorView:
    return ActorView(
        id="hero-1",
        name="Aria",
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


async def _fake_get_situation(db, *, user_id, run_id, recent_limit=None):
    return _situation()


def test_advance_stores_exactly_one_effect(monkeypatch):
    monkeypatch.setattr(playthrough_service, "get_situation", _fake_get_situation)
    flow_nodes.set_runtime(flow_nodes.FlowRuntime(db="db", user_id="user-1", model=None))

    state = _state()
    delta = asyncio.run(flow_nodes.advance(state))

    assert "effect" in delta
    assert isinstance(delta["effect"], DecisionRequest)
    assert delta["effect"].kind == DecisionKind.READ_MOVE


def test_route_after_advance_maps_each_effect_type():
    decision = DecisionRequest(
        decision_id="d1", kind=DecisionKind.READ_MOVE, evidence_ids=(), payload={}
    )
    operation = Operation(operation_id="o1", kind=OperationKind.COMPLETE_ACTION, payload={})
    wait = PlayerWait(request_id="r1", kind="roll", public_payload={})
    beat = BeatRequest(beat_id="b1", kind="outcome", allowed_evidence_ids=(), payload={})
    complete = TurnComplete(status="open")

    assert flow_nodes.route_after_advance(_state(effect=decision)) == "decide"
    assert flow_nodes.route_after_advance(_state(effect=operation)) == "execute"
    assert flow_nodes.route_after_advance(_state(effect=wait)) == "await_player"
    assert flow_nodes.route_after_advance(_state(effect=beat)) == "narrate"
    assert flow_nodes.route_after_advance(_state(effect=complete)) == END


def test_decide_stores_a_decision_result_and_usage(monkeypatch):
    monkeypatch.setattr(playthrough_service, "get_situation", _fake_get_situation)
    scripted = ReadMoveOut(intent="look", refs={}, proposed=None)
    model = ScriptedChatModel([AIMessage(content="looking around"), scripted])
    flow_nodes.set_runtime(flow_nodes.FlowRuntime(db="db", user_id="user-1", model=model))

    request = DecisionRequest(
        decision_id="d1", kind=DecisionKind.READ_MOVE, evidence_ids=(), payload={"text": "look"}
    )
    state = _state(effect=request)

    delta = asyncio.run(flow_nodes.decide(state))

    assert delta["result"].decision_id == "d1"
    assert delta["result"].value.intent == "look"
    assert delta["usage"] is not None


def test_execute_stores_an_operation_result_and_applies_its_delta(monkeypatch):
    monkeypatch.setattr(playthrough_service, "get_situation", _fake_get_situation)
    flow_nodes.set_runtime(flow_nodes.FlowRuntime(db="db", user_id="user-1", model=None))

    op = Operation(
        operation_id="o1", kind=OperationKind.COMPLETE_ACTION, payload={"action_id": "a1"}
    )
    action = ActionCursor(
        action_id="a1",
        actor_id="hero-1",
        kind="attack",
        plan=(OperationSpec(kind=OperationKind.COMPLETE_ACTION, payload={}),),
        step_index=1,
        status="reserved",
        roll_id=None,
        roll_consumed=False,
    )
    state = _state(effect=op, action=action)

    delta = asyncio.run(flow_nodes.execute(state))

    assert delta["result"].operation_id == "o1"
    assert delta["result"].status == "ok"
    assert delta["action"].status == "complete"


def test_narrate_stores_a_draft(monkeypatch):
    monkeypatch.setattr(playthrough_service, "get_situation", _fake_get_situation)
    model = ScriptedChatModel(["A quiet room."])
    flow_nodes.set_runtime(flow_nodes.FlowRuntime(db="db", user_id="user-1", model=model))

    request = BeatRequest(beat_id="beat-1", kind="outcome", allowed_evidence_ids=(), payload={})
    state = _state(effect=request)

    delta = asyncio.run(flow_nodes.narrate(state))

    assert delta["narrative"].draft == "A quiet room."
    assert delta["narrative"].beat_id == "beat-1"
    assert delta["usage"] is not None


def test_await_player_interrupts_then_resumes_with_no_service_call_before_the_pause(monkeypatch):
    called = False

    async def fake_get_situation(db, *, user_id, run_id, recent_limit=None):
        nonlocal called
        called = True
        return _situation()

    monkeypatch.setattr(playthrough_service, "get_situation", fake_get_situation)
    flow_nodes.set_runtime(flow_nodes.FlowRuntime(db="db", user_id="user-1", model=None))

    wait = PlayerWait(
        request_id="req-1",
        kind="roll",
        public_payload={"type": "roll_request", "request_id": "req-1"},
    )

    async def advance_stub(state: GameFlowState):
        return {"effect": wait}

    graph = StateGraph(GameFlowState)
    graph.add_node("advance_stub", advance_stub)
    graph.add_node("await_player", flow_nodes.await_player)
    graph.add_edge(START, "advance_stub")
    graph.add_edge("advance_stub", "await_player")
    graph.add_edge("await_player", END)
    saver = InMemorySaver(serde=checkpointer_service.checkpoint_serde())
    compiled = graph.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": "t1"}}
    result = asyncio.run(compiled.ainvoke(_state(), config=config))

    assert called is False
    interrupts = result["__interrupt__"]
    assert interrupts[0].value == wait.public_payload

    resumed = asyncio.run(compiled.ainvoke(Command(resume={"value": 15}), config=config))

    assert resumed["resume"] == ResumeResult(request_id="req-1", value={"value": 15})
