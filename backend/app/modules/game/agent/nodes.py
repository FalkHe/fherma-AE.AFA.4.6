"""Nodes are factories taking their dependencies as arguments, so tests
build the graph with a scripted model instead of monkeypatching here.
Everything is async because `playthrough.service` is.
"""

import re
from typing import Literal, Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import ToolNode, ToolRuntime
from sqlalchemy import select

from app.core.llm import service as llm_service
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
                select(playthrough_models.GameObject).where(
                    playthrough_models.GameObject.campaign_run_id == ctx.run_id,
                    playthrough_models.GameObject.owner_object_id == char.id,
                )
            )
            carried_items = list(items_result.scalars().all())
            items_str = (
                ", ".join(f"{item.name} (id: {item.id})" for item in carried_items)
                if carried_items
                else "none"
            )

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

            # Present objects & creatures in this scene. Creatures are id
            # first (sprint 010/10, ← finding: several identically-named
            # monsters -- "Goblin Raider" x4 -- gave the model no way to
            # tell them apart, and it aimed a monster's attack at an NPC
            # instead), each tagged `player`/`monster`/`npc`, alive/HP and
            # its own named attacks, via the one shared reader
            # `playthrough_service.describe_scene_creatures` also backs
            # `get_scene` and every combat tool's own actor lookup with.
            scene_creatures = await playthrough_service.describe_scene_creatures(
                ctx.db,
                run_id=ctx.run_id,
                scene_id=current_scene_id,
                campaign_id=campaign_id,
                version=content_version,
            )
            creatures = [
                f"id {c['id']}: {c['name']} ({c['role']}), "
                f"HP {c['current_hp']}/{c['max_hp']}, AC {c['armour_class']}, "
                f"{'alive' if c['is_alive'] else 'down'}, "
                f"attacks: {', '.join(c['attacks']) if c['attacks'] else 'none'}"
                for c in scene_creatures
                if c["role"] != "player"
            ]

            fixtures_items_result = await ctx.db.execute(
                select(playthrough_models.GameObject).where(
                    playthrough_models.GameObject.campaign_run_id == ctx.run_id,
                    playthrough_models.GameObject.scene_id == current_scene_id,
                    playthrough_models.GameObject.owner_object_id.is_(None),
                    playthrough_models.GameObject.kind.in_(("item", "fixture")),
                )
            )
            fixtures_items = [
                f"{obj.name} (id: {obj.id}, kind: {obj.kind})"
                for obj in fixtures_items_result.scalars().all()
            ]

            if creatures:
                scene_info.append(f"- Creatures present: {'; '.join(creatures)}")
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


def _fmt_success(success: bool) -> str:
    return "succeeded" if success else "failed"


async def _turn_mechanics_summary(ctx: DmContext) -> str:
    """This turn's own recorded mechanical facts, read back from the
    events it has actually written so far -- ground truth the narration
    must not contradict (sprint 010/11 round 4, Fault C -- ← finding: a
    `tool_call attack` recorded `hit` while the narration said "fails to
    connect", and a character brought to 0 HP with `down: true` was
    narrated standing "ready for your next move"). Rebuilt fresh on every
    `narrate` call, never only at `load_context`, so it also covers
    whatever the tools node just did this turn.

    Also flags an `attack`/`damage` roll no `attack`/`damage` tool_call has
    consumed yet (Fault B -- ← finding: three monster attack rolls were
    made through `roll_dice` and never followed by `attack`; the model
    decided the miss itself instead) -- `roll_dice(kind="attack"/"damage")`
    stays a legitimate first step (the tool the roll is for `attack`/
    `damage`'s own `roll_id` argument), so it is not refused outright, but
    an unresolved one is called out here as exactly that: unresolved.

    Degrades to `""` exactly `_build_game_context`'s own defensive pattern:
    a test's stub `db` carries no real rows to query, and a turn with no
    `run_id`/`turn_id` yet (there is nothing to summarise) has nothing to
    add either.
    """
    no_context = ctx.db is None or ctx.run_id is None or ctx.turn_id is None
    if no_context or not hasattr(ctx.db, "execute"):
        return ""

    try:
        stmt = (
            select(playthrough_models.Event)
            .where(
                playthrough_models.Event.campaign_run_id == ctx.run_id,
                playthrough_models.Event.turn_id == ctx.turn_id,
            )
            .order_by(playthrough_models.Event.id)
        )
        result = await ctx.db.execute(stmt)
        events = list(result.scalars().all())
    except Exception:
        return ""

    # Every payload is stored through `append_event`'s own `model_dump(by_
    # alias=True)` (`playthrough.service`), so a raw read here -- same as
    # `playthrough.service`'s own `_hit_already_damaged` -- always uses the
    # stored camelCase key (`rollIds`, `actorId`, `targetName`, ...), never
    # the model's snake_case field name.
    consumed_roll_ids = {
        rid
        for event in events
        if event.type == "tool_call"
        for rid in (event.payload.get("rollIds") or [])
    }

    lines: list[str] = []
    for event in events:
        payload = event.payload
        if event.type == "tool_call":
            name = payload.get("name")
            outcome = payload.get("outcome", {})
            args = payload.get("args", {})
            ok = payload.get("result") == "ok"
            if name == "attack":
                if ok:
                    lines.append(
                        f"- ATTACK: {args.get('actorId')} vs {args.get('targetId')} -> "
                        f"{outcome.get('outcome')} (total {outcome.get('total')} vs AC "
                        f"{outcome.get('armourClass')})."
                    )
                else:
                    lines.append(f"- ATTACK refused: {outcome.get('reason')}.")
            elif name == "damage":
                if ok:
                    state = (
                        "DOWN"
                        if outcome.get("down")
                        else ("alive" if outcome.get("isAlive") else "dead")
                    )
                    lines.append(
                        f"- DAMAGE: {args.get('targetId')} took {outcome.get('applied')} damage, "
                        f"HP now {outcome.get('currentHp')} ({state})."
                    )
                else:
                    lines.append(f"- DAMAGE refused: {outcome.get('reason')}.")
            elif name in ("resolve_check", "resolve_save"):
                lines.append(f"- {name.upper()}: {_fmt_success(bool(outcome.get('success')))}.")
            elif name == "passive_check":
                lines.append(
                    f"- PASSIVE CHECK: score {outcome.get('passiveScore')} vs DC "
                    f"{outcome.get('dc')} -> {_fmt_success(bool(outcome.get('success')))}."
                )
        elif event.type == "hp_changed":
            state = "DOWN" if payload.get("down") else ("alive" if payload.get("alive") else "dead")
            lines.append(
                f"- HP CHANGED: {payload.get('targetName')} {payload.get('before')} -> "
                f"{payload.get('after')} ({state})."
            )
        elif (
            event.type == "roll"
            and payload.get("kind") in ("attack", "damage")
            and event.id not in consumed_roll_ids
        ):
            lines.append(
                f"- UNRESOLVED {payload.get('kind')} roll (total {payload.get('total')}) for "
                f"actor {payload.get('actorId')}: no attack/damage tool call has consumed it "
                "yet -- do not narrate a hit, miss, or damage for this roll until it does."
            )

    if not lines:
        return ""

    return (
        "### This Turn's Mechanical Results (ground truth -- do not contradict)\n"
        + "\n".join(lines)
        + "\n\nRule: the results above were decided by the game's own tools, not by you. "
        "Never say an attack landed when it recorded a miss, or missed when it recorded a "
        "hit or crit; never describe any creature -- player character or monster -- as "
        "unharmed, standing, fighting on, or able to act when an HP CHANGED line above marked "
        "it DOWN or dead -- narrate a character down, unconscious or fallen, and a monster "
        "dead, defeated or destroyed, never merely wounded or staggered; and never state a "
        "hit, miss, or damage amount for a roll marked UNRESOLVED above until the matching "
        "attack/damage tool call actually happens."
    )


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
        if last_human is not None and ctx.run_id is not None and ctx.record_action:
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

    async def narrate(state: DmState, *, runtime: ToolRuntime[DmContext]) -> dict:
        context = state.get("context", "")
        parts = [system_prompt]
        if context:
            parts.append(f"## Current Game Context\n{context}")
        # Rebuilt fresh on every call, not only the turn's first (Fault C,
        # ← finding): this node runs again after `tools`, so a mechanic
        # this turn already resolved is ground truth the model must not
        # contradict by the time it narrates.
        mechanics = await _turn_mechanics_summary(runtime.context)
        if mechanics:
            parts.append(mechanics)
        full_system = "\n\n".join(parts)
        system = SystemMessage(content=full_system)
        reply = await llm_service.ainvoke_chat(bound, [system, *state["messages"]], label="narrate")
        return {"messages": [reply]}

    return narrate


def _handle_tool_error(exc: Exception) -> str:
    return f"refused: {exc}"


def make_tools() -> ToolNode:
    # Tool bodies serialise themselves against `ctx.db_lock`
    # (`agent/tools.py`'s `_serialized`) rather than this node reaching
    # for `ToolNode`'s own `awrap_tool_call` hook (sprint 010/11 round 4,
    # Fault A -- ← finding): `ToolNode._arun_one` wraps *that* hook's own
    # call in a bare `except Exception`, with no `GraphBubbleUp` carve-out
    # the way its inner `_execute_tool_async` has -- installing it here,
    # with `handle_tool_errors` set, silently swallowed `ask_player`'s and
    # `request_player_roll`'s own `interrupt()` into an ordinary error
    # message instead of actually pausing the turn.
    return ToolNode(TOOLS, handle_tool_errors=_handle_tool_error)


def _turn_usage(messages: list[BaseMessage]) -> llm_service.Usage:
    """Sum every model call this turn made into one `Usage`.

    "This turn" is every `AIMessage` after the last `HumanMessage` in
    `state["messages"]` -- that boundary survives an interrupt (a question
    or a roll mid-turn), so the whole resumed leg is still counted, never
    just its final call. Token counts add as plain ints; `cost_usd` is the
    sum of whichever calls reported one, or `None` when none did -- a
    provider that never reports cost must not make the turn look free.
    """
    last_human_index = -1
    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            last_human_index = index

    usages = [
        llm_service.usage_of(message)
        for message in messages[last_human_index + 1 :]
        if isinstance(message, AIMessage)
    ]
    costs = [usage.cost_usd for usage in usages if usage.cost_usd is not None]

    return llm_service.Usage(
        prompt_tokens=sum(usage.prompt_tokens for usage in usages),
        completion_tokens=sum(usage.completion_tokens for usage in usages),
        total_tokens=sum(usage.total_tokens for usage in usages),
        cost_usd=sum(costs) if costs else None,
    )


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
                    usage=_turn_usage(state["messages"]),
                )
                await ctx.db.commit()

                run = await playthrough_service.get_campaign_run(
                    ctx.db, user_id=ctx.user_id, run_id=ctx.run_id
                )
                if run.status == "ready":
                    await playthrough_service.activate_campaign_run(
                        ctx.db, user_id=ctx.user_id, run_id=ctx.run_id
                    )
        return {}

    return record_narration


def route_after_narrate(state: DmState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return TOOLS_NODE
    return RECORD_NARRATION
