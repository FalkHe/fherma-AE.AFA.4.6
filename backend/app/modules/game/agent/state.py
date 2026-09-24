"""`DmContext` is the graph's `context_schema`: what the mechanics need and
the model must never be able to supply. It reaches a tool through
`ToolRuntime`, so it is absent from every tool's model-facing schema.
"""

import asyncio
import json
from dataclasses import dataclass, field
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
    record_action: bool = True
    """False suppresses `record_action`'s own `player_action` write (sprint
    010/03) -- the DM-led opening turn, which has no player text to record,
    is the only caller that sets this."""
    db_lock: asyncio.Lock = field(default_factory=asyncio.Lock, compare=False, repr=False)
    """Serialises tool execution against `db` (sprint 010/11 round 4, Fault
    A -- ← finding): LangGraph's `ToolNode` runs a batch of tool calls in
    one `AIMessage` concurrently (`asyncio.gather`), but one `AsyncSession`
    is not safe for concurrent use -- two goblins attacking in the same
    turn corrupted the session mid-flush and left a `roll_requested` with
    no matching `roll`. `agent/nodes.py`'s `make_tools()` wraps every call
    in `async with ctx.db_lock`, so only one tool body runs at a time even
    though several are scheduled concurrently. `compare=False`/`repr=False`
    keep two otherwise-identical contexts equal and printable -- a lock has
    no meaningful equality of its own, only identity."""


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
