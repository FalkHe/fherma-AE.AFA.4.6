"""A tool is the model-facing contract plus a thin call into
`playthrough.service`, which owns every mechanic. The tool docstring is
what the model reads to decide when and how to call it.

`runtime` is injected by `ToolNode` and hidden from the model's schema
(← 005-D2/D6).
"""

from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from app.modules.content import service as content_service
from app.modules.game.agent.state import (
    GET_CAMPAIGN_TOOL,
    GET_OBJECT_TOOL,
    GET_SCENE_TOOL,
    ROLL_DICE_TOOL,
    DmContext,
)
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.schemas import RollKind


async def _resolve_campaign_and_version(
    ctx: DmContext, campaign_id: str | None, version: str | None
) -> tuple[str, str]:
    if campaign_id and version:
        return campaign_id, version
    if ctx.run_id:
        run = await playthrough_service.get_campaign_run(
            ctx.db, user_id=ctx.user_id, run_id=ctx.run_id
        )
        c_id = campaign_id or run.campaign_id
        c_ver = version or run.content_version
        return c_id, c_ver
    raise ValueError("campaign_id and version must be provided when no run_id is in context.")


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


## Content Read Tools
@tool(GET_SCENE_TOOL)
async def get_scene(
    scene_id: str,
    runtime: ToolRuntime[DmContext],
    campaign_id: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Load authored scene facts, exits, secret DCs, NPC intentions, and placement
    references by scene ID."""
    ctx = runtime.context
    c_id, c_ver = await _resolve_campaign_and_version(ctx, campaign_id, version)
    scene = content_service.load_scene(c_id, c_ver, scene_id)
    return scene.model_dump()


@tool(GET_OBJECT_TOOL)
async def get_object(
    object_id: str,
    runtime: ToolRuntime[DmContext],
    campaign_id: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Load an authored object template (creature, item, or fixture) by ID or name,
    including stat blocks, kind, interactions, and attributes."""
    ctx = runtime.context
    c_id, c_ver = await _resolve_campaign_and_version(ctx, campaign_id, version)
    try:
        template = content_service.load_object_template(c_id, c_ver, object_id)
        return template.model_dump()
    except Exception:
        pass

    loaded = content_service.load_campaign(c_id, c_ver)
    for tmpl in loaded.object_templates.values():
        if tmpl.id == object_id or tmpl.name.lower() == object_id.lower():
            return tmpl.model_dump()

    raise ValueError(f"Object template '{object_id}' not found in campaign '{c_id}' ({c_ver}).")


@tool(GET_CAMPAIGN_TOOL)
async def get_campaign(
    runtime: ToolRuntime[DmContext],
    campaign_id: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Load campaign overview, title, summary, adventure list, and seed character template."""
    ctx = runtime.context
    c_id, c_ver = await _resolve_campaign_and_version(ctx, campaign_id, version)
    loaded = content_service.load_campaign(c_id, c_ver)
    return {
        "id": loaded.campaign.id,
        "title": loaded.campaign.title,
        "summary": loaded.campaign.summary,
        "adventures": [
            {
                "id": adv.id,
                "title": adv.title,
                "intro": adv.intro,
                "entry_scene": adv.entry_scene,
                "scenes": [s.id for s in adv.scenes],
            }
            for adv in loaded.adventures.values()
        ],
        "seed_character": loaded.campaign.seed_character.model_dump(),
    }


## Tool registry
TOOLS = [roll_dice, get_scene, get_object, get_campaign]
