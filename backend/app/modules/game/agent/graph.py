"""Composes the five-node game flow (sprint 011/08, WI1) per `docs/general/
game-flow.v2.md` §9.1-9.6: `START` goes straight to `advance`, the control
plane; the single conditional edge leaving `advance` is keyed only on the
type of `state["effect"]` (`flow_nodes.route_after_advance`); every worker
node has exactly one fixed edge back to `advance`. No subgraphs, no
`Command(goto)`, no worker-to-worker edges.

`flow_nodes` reads its runtime (`db`, `user_id`, `model`) from a
module-level `FlowRuntime` -- the caller must call `flow_nodes.set_runtime()`
once per turn before invoking the compiled graph (`game/service.py`, WI2).
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.modules.game.agent import flow_nodes
from app.modules.game.agent.flow_state import (
    GameFlowState,
    NarrativeCursor,
    TurnFrame,
)


def build_graph(
    model: BaseChatModel,
    *,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    graph = StateGraph(GameFlowState)

    graph.add_node("advance", flow_nodes.advance)
    graph.add_node("decide", flow_nodes.decide)
    graph.add_node("execute", flow_nodes.execute)
    graph.add_node("await_player", flow_nodes.await_player)
    graph.add_node("narrate", flow_nodes.narrate)

    graph.add_edge(START, "advance")
    graph.add_conditional_edges(
        "advance",
        flow_nodes.route_after_advance,
        {
            "decide": "decide",
            "execute": "execute",
            "await_player": "await_player",
            "narrate": "narrate",
            END: END,
        },
    )
    graph.add_edge("decide", "advance")
    graph.add_edge("execute", "advance")
    graph.add_edge("await_player", "advance")
    graph.add_edge("narrate", "advance")

    return graph.compile(checkpointer=checkpointer, name="game-flow")


def initial_state(frame: TurnFrame) -> GameFlowState:
    """Every `GameFlowState` key at its empty value for a fresh turn."""
    return GameFlowState(
        turn=frame,
        move=None,
        action=None,
        combat=None,
        awaiting=None,
        resume=None,
        pending_hit_id=None,
        check_outcome=None,
        reactions=[],
        narrative=NarrativeCursor(beat_id=None, draft=None, event_id=None),
        effect=None,
        result=None,
        usage=None,
        error=None,
    )
