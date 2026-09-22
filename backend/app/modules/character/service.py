"""Read-only lookups over the SRD options and class data hand-authored as
Python literals in `options.py` (WI1: `RACES`, `SKILLS`, `ALIGNMENTS`,
`ARMOURS`, `WEAPONS`, `GEAR`, `POINT_BUY`) and `classes.py` (WI2: `CLASSES`).

A module of functions, per `AGENTS.md`'s "services are modules of
functions" rule -- callers do `from . import service`, never `from .service
import races`. Pure: no session, no I/O; every function takes no argument
except the two by-name lookups. The lookup dicts are built once at import
time from the literals above.

`build_creation_agent`/`turn` (sprint 009-03, WI1) are the character
module's own small agent, modelled on `game.service.build_agent`/`turn`;
`render_sheet`/`render_seed`/`render_greeting` are its deterministic,
non-model text -- so a greeting or a review never depends on the model
repeating a name or a number correctly.

`start_creation`/`send_creation_message` (sprint 009-05, WI1) are the two
creation-chat routes' own work: `app.state` holds the lazily built agent
and the live conversations (← research Decision 1), never the database --
nothing here is persisted. `creation_progress` is the pure draft ->
sheet-so-far renderer (← research Decision 3)."""

from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.core.llm.service import chat_model
from app.core.prompts.service import load_prompt
from app.core.tracing import service as tracing
from app.modules.character.agent.state import CreationContext, CreationState
from app.modules.character.classes import CLASSES
from app.modules.character.errors import CharacterBuildError, CreationConversationNotFoundError
from app.modules.character.options import (
    ALIGNMENTS,
    ARMOURS,
    GEAR,
    POINT_BUY,
    RACES,
    SKILLS,
    WEAPONS,
)
from app.modules.character.schemas import (
    Alignment,
    Armour,
    CharacterClass,
    CharacterCreateRequest,
    CharacterSheet,
    ClassName,
    CreationReply,
    CreationStepName,
    GearItem,
    PointBuy,
    Race,
    RaceName,
    SheetSoFar,
    Skill,
    Weapon,
)
from app.modules.content import service as content_service
from app.modules.content.schemas import Abilities, SeedCharacter
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError, CharacterExistsError

CREATION_SYSTEM_PROMPT_ID = "character/system/creator"

# ← research Decision 4: any turn failure (model, tool or graph) answers
# this in-voice line rather than a raw failure; moved here from
# `commands.py` so both the terminal command and the HTTP routes share it.
MODEL_ERROR_REPLY = "The tavern is noisy, I did not catch that. Say it again?"

_ABILITY_ORDER = ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
_ABILITY_ABBR = {
    "strength": "STR",
    "dexterity": "DEX",
    "constitution": "CON",
    "intelligence": "INT",
    "wisdom": "WIS",
    "charisma": "CHA",
}

_RACES_BY_NAME: dict[RaceName, Race] = {race.name: race for race in RACES}
_CLASSES_BY_NAME: dict[ClassName, CharacterClass] = {cls.name: cls for cls in CLASSES}


def races() -> list[Race]:
    return RACES


def classes() -> list[CharacterClass]:
    return CLASSES


def skills() -> list[Skill]:
    return SKILLS


def alignments() -> list[Alignment]:
    return ALIGNMENTS


def armours() -> list[Armour]:
    return ARMOURS


def weapons() -> list[Weapon]:
    return WEAPONS


def gear() -> list[GearItem]:
    return GEAR


def point_buy() -> PointBuy:
    return POINT_BUY


def race(name: RaceName) -> Race:
    return _RACES_BY_NAME[name]


def character_class(name: ClassName) -> CharacterClass:
    return _CLASSES_BY_NAME[name]


def build_sheet(request: CharacterCreateRequest, *, point_buy: bool = True) -> CharacterSheet:
    # Function-local: `builder` imports this module for its own lookups
    # (`race`, `character_class`), so a module-scope import here would be
    # a cycle.
    from app.modules.character import builder

    return builder.build_sheet(request, point_buy=point_buy)


def _modifier(score: int) -> int:
    """The SRD formula (floor division), duplicated in `builder.py` /
    `playthrough.dice` -- a one-line rule, not worth a `core/` promotion."""
    return (score - 10) // 2


def _ability_line(abilities: dict[str, int]) -> str:
    return "  ".join(
        f"{_ABILITY_ABBR[ability]} {abilities[ability]} ({_modifier(abilities[ability]):+d})"
        for ability in _ABILITY_ORDER
    )


def render_sheet(sheet: CharacterSheet) -> str:
    """Deterministic review text for a built character -- name, race,
    class, level 1, alignment, HP, AC, speed, abilities with modifiers,
    saves, skills, equipment, looks, backstory (← D14 §1.12)."""
    equipment = (
        ", ".join(
            f"{item.name} x{item.quantity}" if item.quantity > 1 else item.name
            for item in sheet.equipment
        )
        or "none yet"
    )
    lines = [
        sheet.name,
        f"{sheet.race} {sheet.character_class} - Level {sheet.level} - {sheet.alignment}",
        "",
        f"Hit points {sheet.max_hp}   Armour class {sheet.armour_class}   Speed {sheet.speed} ft",
        "",
        f"Abilities: {_ability_line(sheet.abilities.model_dump())}",
        f"Saving throws: {', '.join(sheet.saving_throws) or 'none'}",
        f"Skills: {', '.join(sheet.skills) or 'none yet'}",
        f"Equipment: {equipment}",
        "",
        f"Looks: {sheet.appearance or 'not told yet'}",
        f"Story: {sheet.backstory or 'not told yet'}",
    ]
    return "\n".join(lines)


def render_seed(seed: SeedCharacter, item_names: list[str] | None = None) -> str:
    """Deterministic review text for the campaign's ready-made hero, the
    same shape as `render_sheet` over `SeedCharacter`'s narrower fields.
    `item_names` prints in place of `seed.inventory`'s bare content ids
    when given (the campaign's own object template names); falls back to
    the ids when not."""
    equipment = ", ".join(item_names) if item_names else ", ".join(seed.inventory)
    lines = [
        seed.name,
        f"{seed.race} {seed.character_class}",
        "",
        f"Hit points {seed.max_hp}   Armour class {seed.armour_class}",
        "",
        f"Abilities: {_ability_line(seed.abilities.model_dump())}",
        f"Equipment: {equipment or 'none yet'}",
        "",
        f"Looks: {seed.appearance}",
        f"Background: {seed.background}",
    ]
    return "\n".join(lines)


def render_greeting(campaign_title: str, seed: SeedCharacter) -> str:
    """Deterministic greeting, printed before the agent's first turn so
    AC1 never depends on the model repeating the seed hero's name right."""
    return (
        f"Well met. You've come for {campaign_title}, and it needs someone to walk into it.\n"
        f"This campaign keeps a hero ready: {seed.name}, a {seed.race} {seed.character_class}. "
        f'Say "take {seed.name}" and you are at the table.\n'
        "Otherwise, tell me who you'd rather be -- anything goes, I'll sort out the rules as "
        "we talk."
    )


@dataclass(frozen=True)
class CreationTurn:
    reply: str
    saved: bool
    # ← research Decision 3: the merged draft this turn left behind, so a
    # caller can render the sheet-so-far without a second read of graph
    # state.
    draft: dict[str, Any] = field(default_factory=dict)


def build_creation_agent(
    *,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    prompt_version: str | None = None,
) -> CompiledStateGraph[CreationState, CreationContext]:
    # Function-local: `agent.tools` imports this module for its own
    # lookups (`build_sheet`, `races`, `classes`), so a module-scope
    # import of `agent.graph` here would be a cycle -- same seam as
    # `build_sheet`'s `builder` import above.
    from app.modules.character.agent.graph import build_graph

    return build_graph(
        model if model is not None else chat_model(),
        system_prompt=load_prompt(CREATION_SYSTEM_PROMPT_ID, version=prompt_version).text,
        checkpointer=checkpointer if checkpointer is not None else InMemorySaver(),
    )


async def turn(
    agent: CompiledStateGraph[CreationState, CreationContext],
    *,
    thread_id: str,
    context: CreationContext,
    player_text: str,
) -> CreationTurn:
    """`show_sheet`'s rendered text (draft or ready-made preview) only
    ever reaches the transcript as a `ToolMessage`, which nothing prints
    on its own (← AC4) -- so this turn's own `show_sheet` results are
    collected and put ahead of the model's closing words, deterministic
    and un-paraphrased. `before` bounds the collection to this turn, so an
    earlier turn's sheet is never repeated."""
    config = RunnableConfig(
        **tracing.langchain_config("creation-turn"), configurable={"thread_id": thread_id}
    )
    before = (await agent.aget_state(config)).values.get("messages", [])
    result: dict[str, Any] = await agent.ainvoke(
        {"messages": [HumanMessage(content=player_text)]}, config=config, context=context
    )
    messages = result.get("messages", [])
    shown = [
        message.content
        for message in messages[len(before) :]
        if isinstance(message, ToolMessage)
        and message.name == "show_sheet"
        and isinstance(message.content, str)
    ]
    closing = messages[-1].text if messages and hasattr(messages[-1], "text") else ""
    reply = "\n\n".join([*shown, closing]) if shown else closing
    return CreationTurn(
        reply=reply, saved=result.get("saved", False), draft=result.get("draft", {})
    )


_CREATION_STEPS: tuple[CreationStepName, ...] = (
    "raceClass",
    "scores",
    "identity",
    "skills",
    "alignment",
    "equipment",
    "review",
)


def _race_class_done(draft: dict[str, Any]) -> bool:
    return bool(draft.get("race")) and bool(draft.get("character_class"))


def _scores_done(draft: dict[str, Any]) -> bool:
    return draft.get("abilities") is not None


def _identity_done(draft: dict[str, Any]) -> bool:
    return bool(draft.get("name"))


def _skills_done(draft: dict[str, Any]) -> bool:
    return draft.get("skills") is not None


def _alignment_done(draft: dict[str, Any]) -> bool:
    return draft.get("alignment") is not None


def _equipment_done(draft: dict[str, Any]) -> bool:
    if draft.get("equipment_defaults"):
        return True
    class_name = draft.get("character_class")
    if class_name is None:
        return False
    cls = character_class(class_name)
    return all(f"equipment_pick_{index}" in draft for index in range(len(cls.equipment)))


_STEP_CHECKS = (
    _race_class_done,
    _scores_done,
    _identity_done,
    _skills_done,
    _alignment_done,
    _equipment_done,
)


def _current_step(draft: dict[str, Any]) -> tuple[CreationStepName, int]:
    for index, done in enumerate(_STEP_CHECKS):
        if not done(draft):
            return _CREATION_STEPS[index], index + 1
    return "review", len(_CREATION_STEPS)


@dataclass(frozen=True)
class CreationProgress:
    sheet: SheetSoFar
    step: CreationStepName
    step_number: int
    can_save: bool


def creation_progress(draft: dict[str, Any]) -> CreationProgress:
    """Pure: the sheet-so-far and the step reached, straight off the
    conversation's own draft dict, no I/O (← research Decision 3). Reuses
    `agent/tools.py`'s own draft -> `CharacterCreateRequest` mapping
    (`_request_from_draft`/`_draft_gaps`) rather than forking it -- since
    `agent.tools` already imports this module at the top, the reverse
    import happens inside this function only, the same cycle-breaking seam
    `build_sheet`/`build_creation_agent` use above.

    `abilities` is always the *final* scores, racial bonus included --
    never the raw point-buy/rolled base a race hasn't been applied to yet
    (← round-1 review): once `build_sheet` succeeds, its own
    `sheet.abilities` is authoritative; before that, if a race and a base
    set of scores are both in the draft, `builder.apply_race` (the same
    helper `build_sheet` itself calls, with no free bonus picked yet --
    `_request_from_draft` never draws one from the draft either) renders
    the same final scores the sheet will end up with. Only with no race
    chosen yet is there no bonus to apply, so the raw draft scores show."""
    from app.modules.character import builder
    from app.modules.character.agent import tools as creation_tools

    step, step_number = _current_step(draft)

    sheet_fields: dict[str, Any] = {
        "name": draft.get("name"),
        "race": draft.get("race"),
        "character_class": draft.get("character_class"),
        "level": 1 if _race_class_done(draft) else None,
        "alignment": draft.get("alignment"),
        "abilities": draft.get("abilities"),
        "appearance": draft.get("appearance"),
        "backstory": draft.get("backstory"),
    }

    sheet = None
    can_save = False
    if not creation_tools._draft_gaps(draft):  # noqa: SLF001 -- reuses the tool's own gap check
        try:
            request = creation_tools._request_from_draft(draft)  # noqa: SLF001
            sheet = build_sheet(request, point_buy=not draft.get("rolled", False))
        except CharacterBuildError:
            sheet = None
        else:
            can_save = True

    if sheet is not None:
        sheet_fields["abilities"] = sheet.abilities.model_dump()
        sheet_fields["max_hp"] = sheet.max_hp
        sheet_fields["armour_class"] = sheet.armour_class
        sheet_fields["speed"] = sheet.speed
        sheet_fields["skills"] = sheet.skills
        sheet_fields["equipment"] = [item.name for item in sheet.equipment]
    elif draft.get("race") and draft.get("abilities") is not None:
        base = Abilities.model_validate(draft["abilities"])
        sheet_fields["abilities"] = builder.apply_race(base, race(draft["race"]), []).model_dump()

    return CreationProgress(
        sheet=SheetSoFar.model_validate(sheet_fields),
        step=step,
        step_number=step_number,
        can_save=can_save,
    )


@dataclass
class _CreationConversation:
    """One live entry of the `app.state` dict `conversationId -> record`
    (← research Decision 1) -- never a database row, so it vanishes with
    the process, and with it any draft nobody saved (← D12)."""

    run_id: str
    user_id: str
    seed: SeedCharacter
    ready_made_items: list[str]
    draft: dict[str, Any] = field(default_factory=dict)


def _creation_agent(state: Any) -> CompiledStateGraph[CreationState, CreationContext]:
    """The one agent per app, built lazily on first use (← research
    Decision 1) so a test's `scripted_model` fixture -- which monkeypatches
    `chat_model` before the first request -- is what `build_creation_agent`
    picks up, never a model built at import time."""
    agent = getattr(state, "creation_agent", None)
    if agent is None:
        agent = build_creation_agent()
        state.creation_agent = agent
    return agent


def _creation_conversations(state: Any) -> dict[str, _CreationConversation]:
    conversations = getattr(state, "creation_conversations", None)
    if conversations is None:
        conversations = {}
        state.creation_conversations = conversations
    return conversations


def _reply_for(
    conversation_id: str, turn_reply: str, *, draft: dict[str, Any], saved: bool, error: bool
) -> CreationReply:
    progress = creation_progress(draft)
    return CreationReply(
        conversation_id=conversation_id,
        reply=turn_reply,
        sheet=progress.sheet,
        step=progress.step,
        step_number=progress.step_number,
        can_save=progress.can_save,
        saved=saved,
        error=error,
    )


async def start_creation(
    db: AsyncSession, state: Any, *, user_id: str, run_id: str
) -> CreationReply:
    """`POST /character/runs/{runId}/creation` (sprint 009-05, WI1): reads
    the run and its members through `playthrough.service.get_run_overview`
    (membership -> 404 for foreign/unknown, ← research Decision 2;
    `unavailable` -> the same 404, since there is no seed hero to greet
    with), refuses a run that already has this caller's character
    (`CharacterExistsError`), then mints an opaque conversation id used
    verbatim as the agent's `thread_id`. The greeting is deterministic
    (`render_greeting`), never a model call (← AC1)."""
    overview = await playthrough_service.get_run_overview(db, user_id=user_id, run_id=run_id)
    if overview.unavailable:
        raise CampaignRunNotFoundError(run_id)
    if any(
        member.user_id == user_id and member.character_name is not None
        for member in overview.members
    ):
        raise CharacterExistsError(run_id)

    loaded = content_service.load_campaign(overview.campaign_id, overview.content_version)
    seed = loaded.campaign.seed_character
    ready_made_items = [loaded.object_templates[item_id].name for item_id in seed.inventory]

    conversation_id = generate_id()
    _creation_conversations(state)[conversation_id] = _CreationConversation(
        run_id=run_id, user_id=user_id, seed=seed, ready_made_items=ready_made_items
    )

    greeting = render_greeting(overview.campaign_title or overview.campaign_id, seed)
    return _reply_for(conversation_id, greeting, draft={}, saved=False, error=False)


async def send_creation_message(
    db: AsyncSession, state: Any, *, conversation_id: str, user_id: str, text: str
) -> CreationReply:
    """`POST /character/creation/{conversationId}/messages` (sprint
    009-05, WI1): re-checks membership on every message (← research
    Decision 2) -- an unknown conversation id, one started by another
    caller, or one whose caller has since lost membership all answer the
    same `CreationConversationNotFoundError` (404). A turn that raises --
    model, tool or graph -- answers 200 with the in-voice line, `error`
    true, and the previous sheet/step (← research Decision 4)."""
    conversation = _creation_conversations(state).get(conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise CreationConversationNotFoundError(conversation_id)

    try:
        await playthrough_service.get_run_overview(db, user_id=user_id, run_id=conversation.run_id)
    except CampaignRunNotFoundError as exc:
        raise CreationConversationNotFoundError(conversation_id) from exc

    agent = _creation_agent(state)
    context = CreationContext(
        db=db,
        user_id=user_id,
        run_id=conversation.run_id,
        ready_made=conversation.seed,
        ready_made_items=conversation.ready_made_items,
    )

    try:
        result = await turn(agent, thread_id=conversation_id, context=context, player_text=text)
    except Exception:  # noqa: BLE001 -- the model, a tool or the graph itself can all raise
        # here (mirrors `commands.py`'s own turn loop); the player sees the
        # in-voice line, never a raw failure (← AC4).
        return _reply_for(
            conversation_id, MODEL_ERROR_REPLY, draft=conversation.draft, saved=False, error=True
        )

    conversation.draft = result.draft
    return _reply_for(
        conversation_id, result.reply, draft=result.draft, saved=result.saved, error=False
    )
