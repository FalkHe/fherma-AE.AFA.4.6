"""Sprint 011/08, WI1 -- the compiled five-node game flow has exactly the
shape §9.1-9.6 describes: one conditional route leaving `advance`, every
worker wired back to it, nothing else."""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START

from app.modules.game.agent.flow_state import NarrativeCursor, TurnFrame
from app.modules.game.agent.graph import build_graph, initial_state

WORKERS = {"decide", "execute", "await_player", "narrate"}


def _turn() -> TurnFrame:
    return TurnFrame(
        run_id="run-1",
        hero_id="hero-1",
        turn_id="turn-1",
        input_kind="action",
        text="I look around",
        status="open",
        round_admitted=True,
    )


def test_the_graph_has_exactly_the_five_flow_nodes():
    agent = build_graph(model=None, checkpointer=InMemorySaver())

    assert set(agent.get_graph().nodes) - {START, END} == {"advance", *WORKERS}


def test_only_advance_has_a_conditional_route():
    agent = build_graph(model=None, checkpointer=InMemorySaver())
    graph = agent.get_graph()

    branch_sources = {edge.source for edge in graph.edges if edge.conditional}

    assert branch_sources == {"advance"}


def test_every_worker_has_exactly_one_fixed_edge_back_to_advance():
    agent = build_graph(model=None, checkpointer=InMemorySaver())
    graph = agent.get_graph()

    for worker in WORKERS:
        fixed_edges = [
            edge for edge in graph.edges if edge.source == worker and not edge.conditional
        ]
        assert len(fixed_edges) == 1
        assert fixed_edges[0].target == "advance"


def test_initial_state_has_every_key_at_its_empty_value():
    frame = _turn()

    state = initial_state(frame)

    assert state == {
        "turn": frame,
        "move": None,
        "action": None,
        "combat": None,
        "awaiting": None,
        "resume": None,
        "pending_hit_id": None,
        "reactions": [],
        "narrative": NarrativeCursor(beat_id=None, draft=None, event_id=None),
        "effect": None,
        "result": None,
        "usage": None,
        "error": None,
    }
