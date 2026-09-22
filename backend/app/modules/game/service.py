"""`game` is the agent layer: it decides, narrates and calls tools. Every
mechanic belongs to `playthrough.service`; nothing here rolls a die or
writes an event.

The model comes from `core/llm/service.chat_model()` so the API-key check
and `max_retries=0` stay in one place. The checkpointer defaults to
`InMemorySaver()` when omitted (e.g. for lightweight testing), or an
`AsyncPostgresSaver` in persistent sessions.

Tests monkeypatch `service.chat_model` and `service.load_prompt`.
"""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from app.core.llm.service import chat_model
from app.core.prompts.service import load_prompt
from app.core.tracing import service as tracing
from app.modules.game.agent.graph import build_graph
from app.modules.game.agent.state import DmContext, DmState, rolls_in

SYSTEM_PROMPT_ID = "game/system/dm"


@dataclass(frozen=True)
class TurnResult:
    reply: str
    rolls: list[dict[str, Any]] = field(default_factory=list)
    interrupt: dict[str, Any] | None = None


def build_agent(
    *,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    prompt_version: str | None = None,
) -> CompiledStateGraph[DmState, DmContext]:
    return build_graph(
        model if model is not None else chat_model(),
        system_prompt=load_prompt(SYSTEM_PROMPT_ID, version=prompt_version).text,
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
    )


def _extract_turn_result(result: dict[str, Any], before_count: int) -> TurnResult:
    interrupt_info = None
    if "__interrupt__" in result and result["__interrupt__"]:
        interrupt_info = result["__interrupt__"][0].value
    messages = result.get("messages", [])
    reply = messages[-1].text if messages and hasattr(messages[-1], "text") else ""
    return TurnResult(
        reply=reply,
        rolls=rolls_in(messages, start=before_count),
        interrupt=interrupt_info,
    )


async def turn(
    agent: CompiledStateGraph[DmState, DmContext],
    *,
    thread_id: str,
    context: DmContext,
    player_text: str,
) -> TurnResult:
    """`rolls` covers this turn only, hence the message count taken before
    invoking."""
    config = RunnableConfig(
        **tracing.langchain_config("dm-turn"), configurable={"thread_id": thread_id}
    )
    before = (await agent.aget_state(config)).values.get("messages", [])
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=player_text)]}, config=config, context=context
    )
    return _extract_turn_result(result, len(before))


async def resume(
    agent: CompiledStateGraph[DmState, DmContext],
    *,
    thread_id: str,
    context: DmContext,
    resume_value: Any,
) -> TurnResult:
    """Resumes a paused agent thread from an interrupt."""
    config = RunnableConfig(
        **tracing.langchain_config("dm-turn"), configurable={"thread_id": thread_id}
    )
    before = (await agent.aget_state(config)).values.get("messages", [])
    result = await agent.ainvoke(Command(resume=resume_value), config=config, context=context)
    return _extract_turn_result(result, len(before))
