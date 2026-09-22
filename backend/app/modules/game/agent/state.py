"""`DmContext` is the graph's `context_schema`: what the mechanics need and
the model must never be able to supply. It reaches a tool through
`ToolRuntime`, so it is absent from every tool's model-facing schema.
"""

import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.graph import MessagesState
from sqlalchemy.ext.asyncio import AsyncSession

ROLL_DICE_TOOL = "roll_dice"
GET_SCENE_TOOL = "get_scene"
GET_OBJECT_TOOL = "get_object"
GET_CAMPAIGN_TOOL = "get_campaign"


@dataclass
class DmContext:
    db: AsyncSession
    user_id: str
    actor_id: str | None = None
    run_id: str | None = None
    turn_id: str | None = None


class DmState(MessagesState):
    pass


def rolls_in(messages: list[AnyMessage], *, start: int = 0) -> list[dict[str, Any]]:
    """`ToolNode` serialises a tool's dict result to a JSON string, so the
    content is parsed here; a dict is accepted for hand-built messages."""
    rolls = []
    for message in messages[start:]:
        if not (isinstance(message, ToolMessage) and message.name == ROLL_DICE_TOOL):
            continue
        payload = message.content
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if isinstance(payload, dict) and "total" in payload:
            rolls.append(payload)
    return rolls
