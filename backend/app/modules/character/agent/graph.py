"""Two nodes only: `talk` proposes, `tools` writes the draft or saves. No
`load_context`, `record_action`/`record_narration` or `guard` -- creation
writes no events, and until `save_character` runs there is nothing to
protect (← research Decision 2).
"""

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from app.modules.character.agent.state import CreationContext, CreationState
from app.modules.character.agent.tools import TOOLS

TALK: Literal["talk"] = "talk"
TOOLS_NODE: Literal["tools"] = "tools"

_TOOL_ERROR_FALLBACK = "The tavern is noisy, I did not catch that. Say it again?"


def _make_talk(model: BaseChatModel, system_prompt: str):
    bound = model.bind_tools(TOOLS)
    system = SystemMessage(content=system_prompt)

    async def talk(state: CreationState) -> dict:
        reply = await bound.ainvoke([system, *state["messages"]])
        return {"messages": [reply]}

    return talk


def _route_after_talk(state: CreationState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return TOOLS_NODE
    return END


def build_graph(
    model: BaseChatModel, *, system_prompt: str, checkpointer: BaseCheckpointSaver
) -> CompiledStateGraph[CreationState, CreationContext]:
    graph = StateGraph(CreationState, context_schema=CreationContext)

    graph.add_node(TALK, _make_talk(model, system_prompt))
    graph.add_node(TOOLS_NODE, ToolNode(TOOLS, handle_tool_errors=_TOOL_ERROR_FALLBACK))

    graph.add_edge(START, TALK)
    graph.add_conditional_edges(TALK, _route_after_talk, {TOOLS_NODE: TOOLS_NODE, END: END})
    graph.add_edge(TOOLS_NODE, TALK)

    return graph.compile(checkpointer=checkpointer, name="creation-agent")
