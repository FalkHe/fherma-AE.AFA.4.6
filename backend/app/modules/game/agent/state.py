"""`DmContext` is the graph's `context_schema`: what the mechanics need and
the model must never be able to supply. It reaches a tool through
`ToolRuntime`, so it is absent from every tool's model-facing schema.
"""

import json
from dataclasses import dataclass
from typing import Any, NotRequired

from langchain_core.messages import AnyMessage, ToolMessage
from langgraph.graph import MessagesState
from sqlalchemy.ext.asyncio import AsyncSession

ROLL_DICE_TOOL = "roll_dice"
GET_SCENE_TOOL = "get_scene"
GET_OBJECT_TOOL = "get_object"
GET_CAMPAIGN_TOOL = "get_campaign"
RESOLVE_CHECK_TOOL = "resolve_check"
RESOLVE_SAVE_TOOL = "resolve_save"
PASSIVE_CHECK_TOOL = "passive_check"
ROLL_INITIATIVE_TOOL = "roll_initiative"
ASK_PLAYER_TOOL = "ask_player"
REQUEST_PLAYER_ROLL_TOOL = "request_player_roll"
INTERACT_TOOL = "interact"
TAKE_TOOL = "take"
DROP_TOOL = "drop"
GIVE_TOOL = "give"
USE_ITEM_TOOL = "use_item"
USE_EXIT_TOOL = "use_exit"
ATTACK_TOOL = "attack"
DAMAGE_TOOL = "damage"
RECALL_TOOL = "recall"
LOOKUP_RULE_TOOL = "lookup_rule"


@dataclass
class DmContext:
    db: AsyncSession
    user_id: str
    actor_id: str | None = None
    run_id: str | None = None
    turn_id: str | None = None


class DmState(MessagesState):
    context: NotRequired[str]


def rolls_in(messages: list[AnyMessage], *, start: int = 0) -> list[dict[str, Any]]:
    """`ToolNode` serialises a tool's dict result to a JSON string, so the
    content is parsed here; a dict is accepted for hand-built messages."""
    rolls = []
    for message in messages[start:]:
        if not (
            isinstance(message, ToolMessage)
            and message.name in (ROLL_DICE_TOOL, REQUEST_PLAYER_ROLL_TOOL)
        ):
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
