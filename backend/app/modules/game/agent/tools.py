"""A tool is the model-facing contract plus a thin call into
`playthrough.service`, which owns every mechanic. The tool docstring is
what the model reads to decide when and how to call it.

`runtime` is injected by `ToolNode` and hidden from the model's schema
(← 005-D2/D6).
"""

import functools
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import interrupt
from pydantic import BaseModel, Field
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
    LOOKUP_RULE_TOOL,
    PASSIVE_CHECK_TOOL,
    RECALL_TOOL,
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
from app.modules.playthrough.errors import (
    GameObjectNotFoundError,
    HitNotUsableError,
    ObjectNotReachableError,
    RollNotUsableError,
)
from app.modules.playthrough.schemas import RollKind
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdCorpusEmptyError


def _serialized(fn):
    """Serialises one tool's whole body against `ctx.db_lock` (sprint
    010/11 round 4, Fault A -- ← finding): `ToolNode` runs a batch of tool
    calls from the same `AIMessage` concurrently (`asyncio.gather`), but
    every tool in one turn shares the same `AsyncSession` through
    `DmContext.db` -- not safe for concurrent use. Two goblins attacking
    in the same turn corrupted the session mid-flush and left a
    `roll_requested` with no matching `roll`.

    Applied directly under `@tool(...)`, closest to each plain `async def`
    -- never through `ToolNode`'s own `awrap_tool_call` hook, which wraps
    a bare `except Exception` around the whole call with no carve-out for
    `ask_player`/`request_player_roll`'s own `interrupt()` (`agent/
    nodes.py`'s `make_tools` has the full account). `functools.wraps`
    keeps the original function's signature visible to `inspect.signature`
    (`follow_wrapped=True` by default), so `@tool`'s own schema
    introspection is unaffected; only the call is serialised, one tool at
    a time, never the model's own request to call several."""

    @functools.wraps(fn)
    async def wrapped(*args, **kwargs):
        runtime = kwargs.get("runtime")
        if runtime is None:
            runtime = next((a for a in args if isinstance(a, ToolRuntime)), None)
        if runtime is None:
            return await fn(*args, **kwargs)
        async with runtime.context.db_lock:
            return await fn(*args, **kwargs)

    return wrapped


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


## Actor resolution -- shared by every tool that rolls or acts for a
## non-default actor (sprint 010/10, ← finding: a scene with several
## identically-named monsters, and the model with no way to tell them
## apart, made a monster's turn silently attack the wrong creature).
async def _living_scene_creatures(
    ctx: DmContext, *, near_actor_id: str | None
) -> list[dict[str, Any]]:
    """The living creatures of the current scene, id first, each with its
    own attack names -- what a lookup failure hands back instead of a bare
    refusal, so the model's next call names a real id."""
    if not ctx.run_id:
        return []
    creatures = await playthrough_service.describe_scene_creatures(
        ctx.db, run_id=ctx.run_id, near_actor_id=near_actor_id
    )
    return [c for c in creatures if c["is_alive"]]


async def _actor_not_found_hint(ctx: DmContext, ref: str) -> dict[str, Any]:
    """The structured, actionable result a lookup failure hands back
    instead of a bare "refused"."""
    return {
        "status": "actor_not_found",
        "message": (
            f"No living creature in this scene has id or name {ref!r}. Re-read the "
            "scene and call again with one of the ids listed in living_creatures."
        ),
        "living_creatures": await _living_scene_creatures(ctx, near_actor_id=ctx.actor_id),
    }


async def _resolve_actor_ref(ctx: DmContext, ref: str) -> str | None:
    """`ref` matched by name against the run's own living creatures
    (`playthrough_service.resolve_actor_ref`), for a caller that already
    tried `ref` as an id and had it refused. `None` when nothing matches
    either -- the caller returns `_actor_not_found_hint` in that case."""
    if not ctx.run_id:
        return None
    try:
        actor = await playthrough_service.resolve_actor_ref(ctx.db, run_id=ctx.run_id, ref=ref)
    except GameObjectNotFoundError:
        return None
    return actor.id


async def _run_for_actor(
    ctx: DmContext, ref: str, call: Callable[[str], Awaitable[Any]]
) -> tuple[str, Any, dict[str, Any] | None]:
    """Runs `call(actor_id)`, first with `ref` as given -- an unchanged id
    still resolves exactly as before, with no extra lookup (existing
    callers, and every test that stubs the mechanic itself, are
    unaffected). Only on `GameObjectNotFoundError` does it retry once
    against `ref` resolved by name. Returns `(actor_id, result, None)` on
    success, or `(ref, None, hint)` -- `hint` a structured, actionable
    result the caller returns as-is -- when neither the id nor a living
    creature's name in this scene matches `ref` at all."""
    try:
        return ref, await call(ref), None
    except GameObjectNotFoundError:
        resolved = await _resolve_actor_ref(ctx, ref)
        if resolved is None:
            return ref, None, await _actor_not_found_hint(ctx, ref)
        return resolved, await call(resolved), None


## Roll Tools
class RollContext(BaseModel):
    """What the server needs to derive a roll's formula, named explicitly
    so the model fills the right fields for `kind` instead of guessing at
    an opaque object (← evidence: an empty `{}` context on an
    `ability_check` used to fail with a bare `KeyError`, which the model
    could not recover from). Which fields matter depends on `kind`:
    `ability_check` / `saving_throw` need `ability` (`dc` and `skill`
    score and label the roll for the player); `attack` / `damage` may
    name `item_id` and/or `attack`; `custom` needs `expression`;
    `initiative` needs nothing. Unused fields are simply left `null`.
    """

    ability: str | None = Field(
        default=None,
        description="Required for ability_check/saving_throw: one of the lowercase SRD "
        "ability names strength, dexterity, constitution, intelligence, wisdom, charisma.",
    )
    skill: str | None = Field(
        default=None,
        description="The named skill for a check (e.g. 'perception'), or null when none applies.",
    )
    dc: int | None = Field(
        default=None, description="Difficulty Class, 1-30, for an ability_check or saving_throw."
    )
    item_id: str | None = Field(
        default=None, description="The weapon/item object id being used, for attack/damage."
    )
    attack: str | None = Field(
        default=None,
        description="Which of the actor's named attacks to use, for attack/damage, when it "
        "has more than one.",
    )
    expression: str | None = Field(
        default=None, description="Dice expression, e.g. '2d6+1' -- required for kind=custom only."
    )


@tool(ROLL_DICE_TOOL)
@_serialized
async def roll_dice(
    kind: RollKind,
    context: RollContext,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
) -> dict[str, Any]:
    """Roll dice for a roll the player does not make themselves: NPCs,
    monsters, hidden rolls, damage, initiative and anything else uncertain
    that is not a player character's ability check or saving throw - those
    go through `request_player_roll` instead. Never invent a result. `kind`
    is one of attack, damage, ability_check, saving_throw, initiative,
    custom. `actor_id` is the acting character's id
    (optional, defaults to current actor). `context` names what the rules need:
    {"ability": "dexterity"} for a check or save, {"attack": "<name>"} for
    attack/damage, {"expression": "2d6+1"} only for kind custom, {} for
    initiative. `actor_id` accepts a creature id or its name (case-
    insensitive, matched against the scene's living creatures) -- always
    prefer the id `get_scene`/the game context already gave you when a
    name could mean more than one creature. The server derives the
    formula from the character sheet; you get back the formula, the
    faces, the modifier and the total. A lookup or attack-name problem
    never refuses bare: it returns `status`, `message` and
    `living_creatures` (id, name, role, HP, attacks) instead, so your next
    call can name the right id and attack."""
    ctx = runtime.context
    ref = actor_id or ctx.actor_id
    if not ref:
        raise ValueError(
            "actor_id is required for roll_dice when no default actor is set in context."
        )

    async def _do_roll(actor: str):
        return await playthrough_service.roll(
            ctx.db,
            user_id=ctx.user_id,
            actor_id=actor,
            kind=kind,
            context=context.model_dump(exclude_none=True),
            visibility="player",
            turn_id=ctx.turn_id,
        )

    try:
        target_actor_id, event, hint = await _run_for_actor(ctx, ref, _do_roll)
    except ValueError as exc:
        if kind not in ("attack", "damage"):
            raise
        return {
            "status": "no_attack",
            "actor_id": ref,
            "message": str(exc),
            "living_creatures": await _living_scene_creatures(ctx, near_actor_id=ctx.actor_id),
        }
    if hint is not None:
        return hint

    payload = event.payload
    result: dict[str, Any] = {
        "roll_id": event.id,
        "kind": payload["kind"],
        "formula": payload["formula"],
        "faces": payload["faces"],
        "modifier": payload["modifier"],
        "total": payload["total"],
    }
    if kind in ("attack", "damage"):
        # Fault B (sprint 010/11 round 4, ← finding): a roll of this kind
        # was made and never followed by the tool that resolves it, and
        # the model decided the outcome itself instead. This number alone
        # is not a hit, a miss, or an HP change -- say so right where the
        # model reads the total, not only in the system prompt.
        result["next_step"] = (
            "This total does not decide hit/miss or damage by itself -- call "
            f"{kind}(roll_id={event.id!r}, ...) next, before narrating anything about it."
        )
    return result


@tool(RESOLVE_CHECK_TOOL)
@_serialized
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
@_serialized
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
@_serialized
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
@_serialized
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
@_serialized
async def get_scene(
    scene_id: str,
    runtime: ToolRuntime[DmContext],
    campaign_id: str | None = None,
    version: str | None = None,
) -> dict[str, Any]:
    """Load authored scene facts, exits, secret DCs, NPC intentions, and placement
    references by scene ID. When a run is in context, also returns
    `creatures_present`: the scene's own live creatures, id first, with
    `role` (player/monster/npc), HP and attack names -- so several
    identically-named monsters can still be told apart and targeted by id
    (sprint 010/10, ← finding)."""
    ctx = runtime.context
    c_id, c_ver = await _resolve_campaign_and_version(ctx, campaign_id, version)
    scene = content_service.load_scene(c_id, c_ver, scene_id)
    result = scene.model_dump()
    if ctx.run_id:
        try:
            result["creatures_present"] = await playthrough_service.describe_scene_creatures(
                ctx.db, run_id=ctx.run_id, scene_id=scene_id, campaign_id=c_id, version=c_ver
            )
        except Exception:
            # Defensive, exactly `agent/nodes.py`'s own `_build_game_context`
            # pattern: a test's stub `db` carries no real rows to query, and
            # this addition must degrade to no creature data rather than
            # break scene loading itself.
            result["creatures_present"] = []
    return result


@tool(GET_OBJECT_TOOL)
@_serialized
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
@_serialized
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
@_serialized
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
@_serialized
async def request_player_roll(
    kind: RollKind,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
    context: RollContext | None = None,
) -> dict[str, Any]:
    """Ask the player to make a roll of `kind` (ability_check, saving_throw,
    initiative, or a rare bespoke custom roll -- never attack or damage,
    which always go through `roll_dice`, for every actor including the
    hero). Use this, never `roll_dice`, for any ability check or saving
    throw made by a player character; the player rolls, not you. Interrupts
    execution and waits for the player to resolve the roll - do not also
    call `roll_dice`, `resolve_check` or `resolve_save` for the same check.
    `actor_id` must be the party's own character (defaults to current
    actor) -- a monster or NPC has no player to ask, and this tool refuses
    it. A monster's attack is never resolved as a hero's saving throw.
    `context` provides mechanics context: for an ability check or saving
    throw, always include `ability`, `skill` (or `null` when none applies)
    and `dc`, e.g. {"ability": "wisdom", "skill": "perception", "dc": 13},
    or {"ability": "dexterity", "skill": null, "dc": 15} for a save. A
    `custom` roll's `context["expression"]` must be a real dice expression
    (e.g. "2d6+1") -- a plain number is refused, never turned into a
    roll."""
    ctx = runtime.context
    target_actor_id = actor_id or ctx.actor_id
    if not target_actor_id:
        raise ValueError(
            "actor_id is required for request_player_roll when no default actor is set in context."
        )
    context_dict = context.model_dump(exclude_none=True) if context is not None else {}

    event = await playthrough_service.request_player_roll(
        ctx.db,
        user_id=ctx.user_id,
        actor_id=target_actor_id,
        kind=kind,
        context=context_dict,
        turn_id=ctx.turn_id,
    )

    interrupt(
        {
            "type": "roll_request",
            "request_id": event.id,
            "kind": kind,
            "formula": event.payload["formula"],
            "actor_id": target_actor_id,
            "context": context_dict,
        }
    )

    # `request_player_roll`/`resolve_roll_request` are both idempotent
    # (playthrough.service), so a resume replaying this coroutine from the
    # top hands back the same `roll_requested` and the same `roll` rather
    # than writing either twice.
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
@_serialized
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
@_serialized
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
@_serialized
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
@_serialized
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
@_serialized
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
@_serialized
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
@_serialized
async def attack(
    target_id: str,
    roll_id: str,
    runtime: ToolRuntime[DmContext],
    actor_id: str | None = None,
    item_id: str | None = None,
    target_name: str | None = None,
) -> dict[str, Any]:
    """Resolve an attack roll against a target creature's armour class.
    `target_id` is the creature being attacked -- it must be one of
    `creatures_present`'s own living entries in the actor's *current*
    scene; never guess an id, and never attack someone the party has not
    actually reached (moving to another scene always goes through
    `use_exit` first).
    `roll_id` is the ID of an attack roll (kind='attack') consumed by this attack.
    `actor_id` is the attacking character/creature (defaults to current actor);
    accepts a creature id or its name, matched case-insensitively against
    the scene's living creatures.
    `item_id` is the weapon/item being used (optional).
    `target_name` is the name of who you mean to strike, exactly as
    `creatures_present` names them (e.g. "Goblin Raider") -- optional, but
    when given it is checked against `target_id`'s own resolved name and
    the attack is refused, not silently redirected, on a mismatch (sprint
    010/11 round 4, Fault D -- ← finding: an attack meant for "the nearest
    goblin raider" landed on the innkeeper instead, because `target_id`
    secretly named her). A lookup problem -- the actor or target not found,
    not in the same scene, or `target_name` not matching `target_id` --
    never refuses bare: it returns `status`, `message` and
    `living_creatures` instead, so your next call can name the right id."""
    ctx = runtime.context
    ref = actor_id or ctx.actor_id
    if not ref:
        raise ValueError("actor_id is required for attack when no default actor is set in context.")

    if target_name is not None:
        creatures = await _living_scene_creatures(ctx, near_actor_id=ctx.actor_id)
        matched = next((c for c in creatures if c["id"] == target_id), None)
        if matched is None or matched["name"].casefold() != target_name.strip().casefold():
            return {
                "status": "target_mismatch",
                "actor_id": ref,
                "target_id": target_id,
                "message": (
                    f"target_name {target_name!r} does not match a living creature with id "
                    f"{target_id!r} in this scene. Re-read creatures_present and call again "
                    "with the id and name of who you actually mean to attack."
                ),
                "living_creatures": creatures,
            }

    async def _do_attack(actor: str) -> str:
        return await playthrough_service.attack(
            ctx.db,
            user_id=ctx.user_id,
            actor_id=actor,
            target_id=target_id,
            item_id=item_id,
            roll_id=roll_id,
            turn_id=ctx.turn_id,
        )

    try:
        target_actor_id, outcome, hint = await _run_for_actor(ctx, ref, _do_attack)
    except (GameObjectNotFoundError, ObjectNotReachableError) as exc:
        return {
            "status": "not_in_scene",
            "actor_id": ref,
            "message": str(exc),
            "living_creatures": await _living_scene_creatures(ctx, near_actor_id=ctx.actor_id),
        }
    if hint is not None:
        return hint

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
@_serialized
async def damage(
    target_id: str,
    roll_id: str,
    hit_id: str,
    runtime: ToolRuntime[DmContext],
) -> dict[str, Any]:
    """Apply damage from a landed attack hit (hit_id) to the target creature.
    `target_id` is the wounded target creature.
    `roll_id` is the ID of a damage roll (kind='damage') consumed by this damage call.
    `hit_id` is the event ID of the landed attack tool_call. A lookup or
    validity problem never refuses bare: it returns `status` and `message`
    (plus `living_creatures` when the target could not be found), so your
    next call can be right."""
    ctx = runtime.context
    try:
        applied = await playthrough_service.damage(
            ctx.db,
            user_id=ctx.user_id,
            target_id=target_id,
            roll_id=roll_id,
            hit_id=hit_id,
            turn_id=ctx.turn_id,
        )
    except GameObjectNotFoundError as exc:
        return {
            "status": "not_found",
            "target_id": target_id,
            "message": str(exc),
            "living_creatures": await _living_scene_creatures(ctx, near_actor_id=ctx.actor_id),
        }
    except (HitNotUsableError, RollNotUsableError) as exc:
        return {
            "status": "rejected",
            "target_id": target_id,
            "message": str(exc),
        }
    return {
        "status": "ok",
        "target_id": target_id,
        "roll_id": roll_id,
        "hit_id": hit_id,
        "applied": applied,
    }


## Memory Tools
@tool(RECALL_TOOL)
@_serialized
async def recall(
    query: str,
    runtime: ToolRuntime[DmContext],
    k: int = 5,
) -> dict[str, Any]:
    """Search past narration and story memories from anywhere in the campaign by semantic meaning.
    `query` is the search phrase or question about past events, characters, or lore.
    `k` is the maximum number of past narrations to retrieve (default 5)."""
    ctx = runtime.context
    if not ctx.run_id:
        return {"status": "ok", "query": query, "items": []}
    items = await playthrough_service.recall(ctx.db, run_id=ctx.run_id, query=query, k=k)
    return {
        "status": "ok",
        "query": query,
        "items": [
            {"id": item.id, "created_at": item.created_at.isoformat(), "text": item.text}
            for item in items
        ],
    }


## Rules Tools
@tool(LOOKUP_RULE_TOOL)
@_serialized
async def lookup_rule(
    query: str,
    runtime: ToolRuntime[DmContext],
    limit: int = 5,
) -> dict[str, Any]:
    """Search official D&D 5e SRD rules, spells, combat mechanics, and conditions.
    `query` is the rules question or keyword (e.g. 'grappling', 'fireball').
    `limit` is the maximum number of matching rule passages to return (default 5)."""
    ctx = runtime.context
    try:
        matches = await srd_service.search_rules(ctx.db, query=query, limit=limit)
    except SrdCorpusEmptyError:
        return {"status": "ok", "query": query, "rules": []}

    if matches and ctx.run_id:
        await playthrough_service.record_rule_lookup(
            ctx.db,
            user_id=ctx.user_id,
            run_id=ctx.run_id,
            topic=matches[0].heading_path,
            turn_id=ctx.turn_id,
        )

    return {
        "status": "ok",
        "query": query,
        "rules": [
            {
                "heading": m.heading_path,
                "text": m.text,
            }
            for m in matches
        ],
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
    recall,
    lookup_rule,
    get_scene,
    get_object,
    get_campaign,
]
