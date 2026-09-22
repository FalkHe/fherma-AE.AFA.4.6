"""Nodes are factories taking their dependencies as arguments, so tests
build the graph with a scripted model instead of monkeypatching here.
Everything is async because `playthrough.service` is.
"""

from typing import Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode, ToolRuntime

from app.modules.game.agent.state import DmContext, DmState
from app.modules.game.agent.tools import TOOLS
from app.modules.playthrough import service as playthrough_service

RECORD_ACTION: Literal["record_action"] = "record_action"
NARRATE: Literal["narrate"] = "narrate"
TOOLS_NODE: Literal["tools"] = "tools"
RECORD_NARRATION: Literal["record_narration"] = "record_narration"


class Node(Protocol):
    """LangGraph calls a node with the keyword `state`; a positional-only
    `Callable[[DmState], dict]` does not type-check against that."""

    async def __call__(self, state: DmState, **kwargs) -> dict: ...


def make_record_action() -> Node:
    async def record_action(state: DmState, *, runtime: ToolRuntime[DmContext]) -> dict:
        ctx = runtime.context
        last_human = next(
            (msg for msg in reversed(state["messages"]) if isinstance(msg, HumanMessage)),
            None,
        )
        if last_human is not None and ctx.run_id is not None:
            text = (
                last_human.content
                if isinstance(last_human.content, str)
                else str(last_human.content)
            )
            await playthrough_service.append_event(
                ctx.db,
                run_id=ctx.run_id,
                type="player_action",
                visibility="player",
                payload={"text": text},
                turn_id=ctx.turn_id,
            )
            await ctx.db.commit()
        return {}

    return record_action


def make_narrate(model: BaseChatModel, system_prompt: str) -> Node:
    bound = model.bind_tools(TOOLS)
    system = SystemMessage(content=system_prompt)

    async def narrate(state: DmState) -> dict:
        reply = await bound.ainvoke([system, *state["messages"]])
        return {"messages": [reply]}

    return narrate


def _handle_tool_error(exc: Exception) -> str:
    return f"refused: {exc}"


def make_tools() -> ToolNode:
    return ToolNode(TOOLS, handle_tool_errors=_handle_tool_error)


def make_record_narration() -> Node:
    async def record_narration(state: DmState, *, runtime: ToolRuntime[DmContext]) -> dict:
        ctx = runtime.context
        last_ai = next(
            (msg for msg in reversed(state["messages"]) if isinstance(msg, AIMessage)),
            None,
        )
        if last_ai is not None and ctx.run_id is not None:
            text = (
                last_ai.text
                if hasattr(last_ai, "text") and last_ai.text
                else (last_ai.content if isinstance(last_ai.content, str) else str(last_ai.content))
            )
            if text:
                await playthrough_service.append_event(
                    ctx.db,
                    run_id=ctx.run_id,
                    type="narration",
                    visibility="player",
                    payload={"text": text},
                    turn_id=ctx.turn_id,
                )
                await ctx.db.commit()
        return {}

    return record_narration


def route_after_narrate(state: DmState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return TOOLS_NODE
    return RECORD_NARRATION
