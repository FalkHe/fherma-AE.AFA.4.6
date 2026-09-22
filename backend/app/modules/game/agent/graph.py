"""Planned additions - the guard node before `narrate`, state validation
after `tools`, the `ask_player` interrupt - each become a named node here,
not logic hidden inside an existing one.
"""

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.modules.game.agent import nodes
from app.modules.game.agent.state import DmContext, DmState


def build_graph(
    model: BaseChatModel, *, system_prompt: str, checkpointer: BaseCheckpointSaver
) -> CompiledStateGraph[DmState, DmContext]:
    graph = StateGraph(DmState, context_schema=DmContext)

    ## Nodes
    graph.add_node(nodes.RECORD_ACTION, nodes.make_record_action())
    graph.add_node(nodes.NARRATE, nodes.make_narrate(model, system_prompt))
    graph.add_node(nodes.TOOLS_NODE, nodes.make_tools())
    graph.add_node(nodes.RECORD_NARRATION, nodes.make_record_narration())

    ## Edges
    graph.add_edge(START, nodes.RECORD_ACTION)
    graph.add_edge(nodes.RECORD_ACTION, nodes.NARRATE)
    graph.add_conditional_edges(
        nodes.NARRATE,
        nodes.route_after_narrate,
        {nodes.TOOLS_NODE: nodes.TOOLS_NODE, nodes.RECORD_NARRATION: nodes.RECORD_NARRATION},
    )
    graph.add_edge(nodes.TOOLS_NODE, nodes.NARRATE)
    graph.add_edge(nodes.RECORD_NARRATION, END)

    return graph.compile(checkpointer=checkpointer, name="dungeon-master")
