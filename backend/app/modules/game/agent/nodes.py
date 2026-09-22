"""Nodes are factories taking their dependencies as arguments, so tests
build the graph with a scripted model instead of monkeypatching here.
Everything is async because `playthrough.service` is.
"""

import re
from typing import Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode, ToolRuntime
from sqlalchemy import select

from app.modules.content import service as content_service
from app.modules.game.agent.state import DmContext, DmState
from app.modules.game.agent.tools import TOOLS
from app.modules.playthrough import models as playthrough_models
from app.modules.playthrough import service as playthrough_service

LOAD_CONTEXT: Literal["load_context"] = "load_context"
RECORD_ACTION: Literal["record_action"] = "record_action"
GUARD: Literal["guard"] = "guard"
NARRATE: Literal["narrate"] = "narrate"
TOOLS_NODE: Literal["tools"] = "tools"
RECORD_NARRATION: Literal["record_narration"] = "record_narration"


GUARD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(?:ignore|disregard|forget)\s+(?:all\s+)?(?:previous|prior|above)\s+instructions\b",
            re.I,
        ),
        "I cannot ignore or override my core Dungeon Master instructions. "
        "Please describe your character's actions within the game world.",
    ),
    (
        re.compile(
            r"\b(?:system\s*prompt|system\s*instruction|developer\s*mode|jailbreak|DAN\s*mode)\b",
            re.I,
        ),
        "I am your Dungeon Master and cannot reveal or alter system instructions. "
        "What would your character like to do?",
    ),
    (
        re.compile(r"\b(?:you\s+are\s+now\s+an?\s+unrestricted|override\s+system)\b", re.I),
        "I cannot alter my role as Dungeon Master. "
        "Please continue by declaring your in-game action.",
    ),
    (
        re.compile(
            r"\b(?:my\s+(?:current\s+)?(?:hp|hit\s*points)\s+(?:is|are|=|set\s+to)\s+\d+|set\s+(?:my\s+)?(?:hp|hit\s*points)\s+to\s+\d+)\b",
            re.I,
        ),
        "State changes such as HP adjustments must be resolved through game mechanics "
        "and dice rolls, not declared directly. What action is your character attempting?",
    ),
    (
        re.compile(
            r"\b(?:i\s+have\s+(?:infinite|max)\s+hp|i\s+am\s+invincible)\b",
            re.I,
        ),
        "Invulnerability cannot be granted out-of-band. "
        "Game outcomes are determined by the rules and rolls.",
    ),
    (
        re.compile(
            r"\b(?:give\s+myself\s+\d+\s+gold|set\s+(?:my\s+)?gold\s+to\s+\d+|my\s+gold\s+is\s+\d+)\b",
            re.I,
        ),
        "Inventory and wealth cannot be modified out-of-band. "
        "Items and gold must be acquired through in-game actions.",
    ),
    (
        re.compile(
            r"\b(?:set\s+(?:my\s+)?level\s+to\s+\d+|i\s+level\s+up\s+to\s+\d+|set\s+(?:my\s+)?(?:str|dex|con|int|wis|cha|strength|dexterity|constitution|intelligence|wisdom|charisma)\s+to\s+\d+)\b",
            re.I,
        ),
        "Character statistics and levels cannot be changed out-of-band. "
        "They are determined by your character sheet and gameplay progression.",
    ),
]


class Node(Protocol):
    """LangGraph calls a node with the keyword `state`; a positional-only
    `Callable[[DmState], dict]` does not type-check against that."""

    async def __call__(self, state: DmState, **kwargs) -> dict: ...


async def _build_game_context(ctx: DmContext) -> str:
    if ctx.db is None or ctx.run_id is None or not hasattr(ctx.db, "execute"):
        return ""

    try:
        sections = []

        # 1. Campaign & Run
        run_result = await ctx.db.execute(
            select(playthrough_models.CampaignRun).where(
                playthrough_models.CampaignRun.id == ctx.run_id
            )
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            return ""

        campaign_id = run.campaign_id
        content_version = run.content_version

        # 2. Party Characters
        char_result = await ctx.db.execute(
            select(playthrough_models.GameObject).where(
                playthrough_models.GameObject.campaign_run_id == ctx.run_id,
                playthrough_models.GameObject.kind == "creature",
                playthrough_models.GameObject.member_id.is_not(None),
            )
        )
        characters = list(char_result.scalars().all())

        current_scene_id = None
        party_lines = []
        for char in characters:
            if current_scene_id is None and char.scene_id:
                current_scene_id = char.scene_id

            # Carried items
            items_result = await ctx.db.execute(
                select(playthrough_models.GameObject.name).where(
                    playthrough_models.GameObject.campaign_run_id == ctx.run_id,
                    playthrough_models.GameObject.owner_object_id == char.id,
                )
            )
            carried_items = list(items_result.scalars().all())
            items_str = ", ".join(carried_items) if carried_items else "none"

            status_str = "alive" if char.is_alive else "unconscious/dead"
            party_lines.append(
                f"- {char.name} (id: {char.id}): HP {char.current_hp}/{char.max_hp}, "
                f"AC {char.armour_class}, status: {status_str}, carried items: [{items_str}]"
            )

        if party_lines:
            sections.append("### Party Status\n" + "\n".join(party_lines))

        # 3. Scene Context
        if current_scene_id:
            scene_info = [f"- Scene ID: {current_scene_id}"]
            try:
                scene = content_service.load_scene(campaign_id, content_version, current_scene_id)
                scene_info.append(f"- Title: {scene.title}")
                if scene.truth:
                    scene_info.append(f"- Facts: {'; '.join(scene.truth)}")
                if scene.npc_intent:
                    scene_info.append(f"- NPC intent: {scene.npc_intent}")
                if scene.exits:
                    exits_str = ", ".join(
                        f"{e.id} ({e.description}) -> {e.to or 'end'}" for e in scene.exits
                    )
                    scene_info.append(f"- Exits: {exits_str}")
            except Exception:
                pass

            # Present objects & creatures in this scene
            scene_objs_result = await ctx.db.execute(
                select(playthrough_models.GameObject).where(
                    playthrough_models.GameObject.campaign_run_id == ctx.run_id,
                    playthrough_models.GameObject.scene_id == current_scene_id,
                    playthrough_models.GameObject.owner_object_id.is_(None),
                )
            )
            scene_objects = list(scene_objs_result.scalars().all())
            creatures = [
                f"{obj.name} (id: {obj.id}, HP: {obj.current_hp}/{obj.max_hp}, "
                f"AC: {obj.armour_class})"
                for obj in scene_objects
                if obj.kind == "creature" and obj.member_id is None
            ]
            fixtures_items = [
                f"{obj.name} (id: {obj.id}, kind: {obj.kind})"
                for obj in scene_objects
                if obj.kind in ("item", "fixture")
            ]

            if creatures:
                scene_info.append(f"- Creatures present: {', '.join(creatures)}")
            if fixtures_items:
                scene_info.append(f"- Objects & fixtures: {', '.join(fixtures_items)}")

            sections.append("### Current Scene\n" + "\n".join(scene_info))

        # 4. Awaiting State
        try:
            awaiting = await playthrough_service.get_awaiting(
                ctx.db, user_id=ctx.user_id, run_id=ctx.run_id
            )
            if awaiting != "none":
                sections.append(f"### Awaiting\n- {awaiting}")
        except Exception:
            pass

        # 5. Recent Recap
        try:
            recaps = await playthrough_service.recap(ctx.db, run_id=ctx.run_id, n=5)
            if recaps:
                recap_lines = [f"- {r.text}" for r in recaps if r.text.strip()]
                if recap_lines:
                    sections.append("### Recent Narrative Recap\n" + "\n".join(recap_lines))
        except Exception:
            pass

        return "\n\n".join(sections)
    except Exception:
        return ""


def make_load_context() -> Node:
    async def load_context(state: DmState, *, runtime: ToolRuntime[DmContext]) -> dict:
        ctx = runtime.context
        context_text = await _build_game_context(ctx)
        return {"context": context_text}

    return load_context


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


def make_guard() -> Node:
    async def guard(state: DmState) -> dict:
        last_human = next(
            (msg for msg in reversed(state["messages"]) if isinstance(msg, HumanMessage)),
            None,
        )
        if last_human is not None:
            text = (
                last_human.content
                if isinstance(last_human.content, str)
                else str(last_human.content)
            )
            for pattern, refusal in GUARD_PATTERNS:
                if pattern.search(text):
                    return {"messages": [AIMessage(content=refusal)]}
        return {}

    return guard


def route_after_guard(state: DmState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage):
        return RECORD_NARRATION
    return NARRATE


def make_narrate(model: BaseChatModel, system_prompt: str) -> Node:
    bound = model.bind_tools(TOOLS)

    async def narrate(state: DmState) -> dict:
        context = state.get("context", "")
        if context:
            full_system = f"{system_prompt}\n\n## Current Game Context\n{context}"
        else:
            full_system = system_prompt
        system = SystemMessage(content=full_system)
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
