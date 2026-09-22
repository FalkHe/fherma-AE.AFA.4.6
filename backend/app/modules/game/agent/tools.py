"""A tool is the model-facing contract plus a thin call into
`playthrough.service`, which owns every mechanic. The tool docstring is
what the model reads to decide when and how to call it.

`runtime` is injected by `ToolNode` and hidden from the model's schema
(← 005-D2/D6).
"""

from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt
from sqlalchemy import select

from app.modules.content import service as content_service
from app.modules.game.agent.state import (
    ASK_PLAYER_TOOL,
    ATTACK_TOOL,
    DAMAGE_TOOL,
    DROP_TOOL,
    GET_CAMPAIGN_TOOL,
    GET_OBJECT_TOOL,
    GET_SCENE_TOOL,
    GIVE_TOOL,
    INTERACT_TOOL,
    PASSIVE_CHECK_TOOL,
    REQUEST_PLAYER_ROLL_TOOL,
    RESOLVE_CHECK_TOOL,
    RESOLVE_SAVE_TOOL,
    ROLL_DICE_TOOL,
    ROLL_INITIATIVE_TOOL,
    TAKE_TOOL,
    USE_EXIT_TOOL,
    USE_ITEM_TOOL,
    DmContext,
)
from app.modules.playthrough import models as playthrough_models
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
        "roll_id": event.id,
        "kind": payload["kind"],
        "formula": payload["formula"],
        "faces": payload["faces"],
        "modifier": payload["modifier"],
        "total": payload["total"],
    }


@tool(RESOLVE_CHECK_TOOL)
async def resolve_check(
    roll_id: str,
    dc: int,
    runtime: ToolRuntime[DmContext],
) -> dict[str, Any]:
    """Resolve an ability check roll against a Difficulty Class (DC 1-30).
    Consumes the roll event identified by `roll_id`. Returns whether the check succeeded."""
    ctx = runtime.context
    success = await playthrough_service.resolve_check(
        ctx.db,
        user_id=ctx.user_id,
        roll_id=roll_id,
        dc=dc,
        turn_id=ctx.turn_id,
    )
    return {"success": success, "dc": dc, "roll_id": roll_id}


@tool(RESOLVE_SAVE_TOOL)
async def resolve_save(
    roll_id: str,
    dc: int,
    runtime: ToolRuntime[DmContext],
) -> dict[str, Any]:
    """Resolve a saving throw roll against a Difficulty Class (DC 1-30).
    Consumes the roll event identified by `roll_id`. Returns whether the save succeeded."""
    ctx = runtime.context
    success = await playthrough_service.resolve_save(
        ctx.db,
        user_id=ctx.user_id,
        roll_id=roll_id,
        dc=dc,
        turn_id=ctx.turn_id,
    )
    return {"success": success, "dc": dc, "roll_id": roll_id}


@tool(PASSIVE_CHECK_TOOL)
async def passive_check(
    ability: str,
    dc: int,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Evaluate a passive ability score (10 + ability modifier) against a DC without rolling dice.
    `ability` is one of strength, dexterity, constitution, intelligence, wisdom, charisma.
    `actor_id` is optional, defaulting to the current actor in context."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError(
            "actor_id is required for passive_check when no default actor is set in context."
        )
    success = await playthrough_service.passive_check(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        ability=ability,
        dc=dc,
        turn_id=ctx.turn_id,
    )
    return {
        "success": success,
        "dc": dc,
        "ability": ability,
        "actor_id": target_actor_id,
    }


@tool(ROLL_INITIATIVE_TOOL)
async def roll_initiative(
    side_a_ids: list[str],
    side_b_ids: list[str],
    runtime: ToolRuntime[DmContext],
) -> dict[str, Any]:
    """Roll initiative for two opposing sides to determine turn order.
    `side_a_ids` and `side_b_ids` are lists of actor IDs for each side."""
    ctx = runtime.context
    event_a, event_b = await playthrough_service.roll_initiative(
        ctx.db,
        user_id=ctx.user_id,
        side_a_ids=side_a_ids,
        side_b_ids=side_b_ids,
        turn_id=ctx.turn_id,
    )
    return {
        "side_a": {
            "id": event_a.id,
            "type": event_a.type,
            "payload": event_a.payload,
        },
        "side_b": {
            "id": event_b.id,
            "type": event_b.type,
            "payload": event_b.payload,
        },
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


## Interrupt Tools
@tool(ASK_PLAYER_TOOL)
async def ask_player(
    text: str,
    options: list[str],
    runtime: ToolRuntime[DmContext],
) -> str:
    """Put a question to the player with explicit options when clarification or a choice is needed.
    Interrupts the turn to ask the player and resumes with the player's chosen answer.
    `text` is the question to ask. `options` is a list of option strings."""
    ctx = runtime.context
    if not ctx.run_id:
        raise ValueError("run_id is required for ask_player.")

    event = await playthrough_service.ask_player(
        ctx.db,
        user_id=ctx.user_id,
        run_id=ctx.run_id,
        text=text,
        options=options,
        turn_id=ctx.turn_id,
    )
    answer = interrupt(
        {
            "type": "question",
            "question_id": event.id,
            "text": text,
            "options": options,
        }
    )
    return f"Player answered: {answer}"


@tool(REQUEST_PLAYER_ROLL_TOOL)
async def request_player_roll(
    kind: RollKind,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ask the player to make a roll of `kind` (ability_check, saving_throw, attack, etc).
    Interrupts execution and waits for the player to resolve the roll.
    `actor_id` is the character making the roll (defaults to current actor).
    `context` provides mechanics context: e.g. {"ability": "dexterity"} for check/save."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError(
            "actor_id is required for request_player_roll when no default actor is set in context."
        )

    event = await playthrough_service.request_player_roll(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        kind=kind,
        context=context or {},
        turn_id=ctx.turn_id,
    )

    interrupt(
        {
            "type": "roll_request",
            "request_id": event.id,
            "kind": kind,
            "formula": event.payload["formula"],
            "actor_id": target_actor_id,
            "context": context or {},
        }
    )

    # Check if a roll answering this request was already recorded before resume
    run_id = getattr(event, "campaign_run_id", ctx.run_id)
    roll_event = None
    if run_id:
        stmt = select(playthrough_models.Event).where(
            playthrough_models.Event.campaign_run_id == run_id,
            playthrough_models.Event.type == "roll",
        )
        result = await ctx.db.execute(stmt)
        roll_event = next(
            (
                e
                for e in result.scalars().all()
                if isinstance(getattr(e, "payload", None), dict)
                and e.payload.get("request_id") == event.id
            ),
            None,
        )
    if roll_event is None:
        roll_event = await playthrough_service.resolve_roll_request(
            ctx.db,
            user_id=ctx.user_id,
            request_id=event.id,
            turn_id=ctx.turn_id,
        )

    payload = roll_event.payload
    return {
        "roll_id": roll_event.id,
        "kind": payload["kind"],
        "formula": payload["formula"],
        "faces": payload["faces"],
        "modifier": payload["modifier"],
        "total": payload["total"],
    }


## Action Tools
@tool(INTERACT_TOOL)
async def interact(
    object_id: str,
    action: str,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
    roll_id: str | None = None,
) -> dict[str, Any]:
    """Interact with a fixture in the scene to perform an authored action (e.g. open, pick_lock).
    `object_id` is the fixture object ID in the scene.
    `action` is the exact authored action string (e.g. 'open', 'pick_lock', 'force_open').
    `actor_id` is the acting character ID (defaults to current actor).
    `roll_id` is the ID of an ability_check roll if required by the action."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError(
            "actor_id is required for interact when no default actor is set in context."
        )

    passed = await playthrough_service.interact(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        object_id=object_id,
        action=action,
        roll_id=roll_id,
        turn_id=ctx.turn_id,
    )
    return {
        "status": "ok",
        "action": action,
        "object_id": object_id,
        "actor_id": target_actor_id,
        "passed": passed,
    }


@tool(TAKE_TOOL)
async def take(
    item_id: str,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Pick up an item from the current scene or an open container into inventory.
    `item_id` is the item object ID.
    `actor_id` is the acting character ID (defaults to current actor)."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError("actor_id is required for take when no default actor is set in context.")

    await playthrough_service.take(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        item_id=item_id,
        turn_id=ctx.turn_id,
    )
    return {
        "status": "ok",
        "action": "take",
        "item_id": item_id,
        "actor_id": target_actor_id,
    }


@tool(DROP_TOOL)
async def drop(
    item_id: str,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Drop an item currently carried by the actor into the scene.
    `item_id` is the item object ID carried in inventory.
    `actor_id` is the acting character ID (defaults to current actor)."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError("actor_id is required for drop when no default actor is set in context.")

    await playthrough_service.drop(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        item_id=item_id,
        turn_id=ctx.turn_id,
    )
    return {
        "status": "ok",
        "action": "drop",
        "item_id": item_id,
        "actor_id": target_actor_id,
    }


@tool(GIVE_TOOL)
async def give(
    item_id: str,
    to_id: str,
    runtime: ToolRuntime[DmContext],
    from_id: str | None = None,
) -> dict[str, Any]:
    """Hand an item carried by one character/creature to another creature in the same scene.
    `item_id` is the item object ID carried by the giver.
    `to_id` is the recipient creature object ID.
    `from_id` is the giving character/creature ID (defaults to current actor)."""
    ctx = runtime.context
    giver_id = from_id or ctx.actor_id
    if not giver_id:
        raise ValueError("from_id is required for give when no default actor is set in context.")

    await playthrough_service.give(
        ctx.db,
        user_id=ctx.user_id,
        from_id=giver_id,
        to_id=to_id,
        item_id=item_id,
        turn_id=ctx.turn_id,
    )
    return {
        "status": "ok",
        "action": "give",
        "item_id": item_id,
        "from_id": giver_id,
        "to_id": to_id,
    }


@tool(USE_ITEM_TOOL)
async def use_item(
    item_id: str,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
    target_id: str | None = None,
) -> dict[str, Any]:
    """Use a consumable item from the actor's inventory.
    `item_id` is the item object ID.
    `actor_id` is the character using the item (defaults to current actor).
    `target_id` is the optional target creature or object ID."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError(
            "actor_id is required for use_item when no default actor is set in context."
        )

    await playthrough_service.use_item(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        item_id=item_id,
        target_id=target_id,
        turn_id=ctx.turn_id,
    )
    return {
        "status": "ok",
        "action": "use_item",
        "item_id": item_id,
        "actor_id": target_actor_id,
        "target_id": target_id,
    }


@tool(USE_EXIT_TOOL)
async def use_exit(
    exit_id: str,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Move a character through an exit in the current scene to a new scene or adventure completion.
    `exit_id` is the exit identifier on the current scene.
    `actor_id` is the character moving (defaults to current actor)."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError(
            "actor_id is required for use_exit when no default actor is set in context."
        )

    await playthrough_service.use_exit(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        exit_id=exit_id,
    )
    return {
        "status": "ok",
        "action": "use_exit",
        "exit_id": exit_id,
        "actor_id": target_actor_id,
    }


## Combat Tools
@tool(ATTACK_TOOL)
async def attack(
    target_id: str,
    roll_id: str,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    """Resolve an attack roll against a target creature's armour class.
    `target_id` is the creature being attacked.
    `roll_id` is the ID of an attack roll (kind='attack') consumed by this attack.
    `actor_id` is the attacking character/creature (defaults to current actor).
    `item_id` is the weapon/item being used (optional)."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError("actor_id is required for attack when no default actor is set in context.")

    outcome = await playthrough_service.attack(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        target_id=target_id,
        item_id=item_id,
        roll_id=roll_id,
        turn_id=ctx.turn_id,
    )

    hit_id = None
    if outcome in ("hit", "crit"):
        stmt = (
            select(playthrough_models.Event.id)
            .where(
                playthrough_models.Event.type == "tool_call",
                playthrough_models.Event.turn_id == ctx.turn_id,
            )
            .order_by(playthrough_models.Event.id.desc())
            .limit(1)
        )
        result = await ctx.db.execute(stmt)
        hit_id = result.scalar_one_or_none()

    return {
        "status": "ok",
        "outcome": outcome,
        "actor_id": target_actor_id,
        "target_id": target_id,
        "item_id": item_id,
        "roll_id": roll_id,
        "hit_id": hit_id,
    }


@tool(DAMAGE_TOOL)
async def damage(
    target_id: str,
    roll_id: str,
    hit_id: str,
    runtime: ToolRuntime[DmContext],
) -> dict[str, Any]:
    """Apply damage from a landed attack hit (hit_id) to the target creature.
    `target_id` is the wounded target creature.
    `roll_id` is the ID of a damage roll (kind='damage') consumed by this damage call.
    `hit_id` is the event ID of the landed attack tool_call."""
    ctx = runtime.context
    applied = await playthrough_service.damage(
        ctx.db,
        user_id=ctx.user_id,
        target_id=target_id,
        roll_id=roll_id,
        hit_id=hit_id,
        turn_id=ctx.turn_id,
    )
    return {
        "status": "ok",
        "target_id": target_id,
        "roll_id": roll_id,
        "hit_id": hit_id,
        "applied": applied,
    }


## Tool registry
TOOLS = [
    roll_dice,
    resolve_check,
    resolve_save,
    passive_check,
    roll_initiative,
    ask_player,
    request_player_roll,
    interact,
    take,
    drop,
    give,
    use_item,
    use_exit,
    attack,
    damage,
    get_scene,
    get_object,
    get_campaign,
]
