"""A tool is the model-facing contract plus a thin call into
`playthrough.service`, which owns every mechanic. The tool docstring is
what the model reads to decide when and how to call it.

`runtime` is injected by `ToolNode` and hidden from the model's schema
(← 005-D2/D6).
"""

from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from app.modules.game.agent.state import ROLL_DICE_TOOL, DmContext
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.schemas import RollKind


## Roll Tools
@tool(ROLL_DICE_TOOL)
async def roll_dice(
    kind: RollKind,
    context: dict[str, Any],
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Roll dice for an actor. Call this for every roll - never
    invent a result. `kind` is one of attack, damage, ability_check,
    saving_throw, initiative, custom. `actor_id` is the acting character's id
    (optional, defaults to current actor). `context` names what the rules need:
    {"ability": "dexterity"} for a check or save, {"attack": "<name>"} for
    attack/damage, {"expression": "2d6+1"} only for kind custom, {} for
    initiative. The server derives the formula from the character sheet;
    you get back the formula, the faces, the modifier and the total."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError(
            "actor_id is required for roll_dice when no default actor is set in context."
        )
    event = await playthrough_service.roll(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        kind=kind,
        context=context,
        visibility="player",
        turn_id=ctx.turn_id,
    )
    payload = event.payload
    return {
        "kind": payload["kind"],
        "formula": payload["formula"],
        "faces": payload["faces"],
        "modifier": payload["modifier"],
        "total": payload["total"],
    }


## Tool registry
TOOLS = [roll_dice]
