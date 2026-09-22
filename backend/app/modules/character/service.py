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
repeating a name or a number correctly."""

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from app.core.llm.service import chat_model
from app.core.prompts.service import load_prompt
from app.core.tracing import service as tracing
from app.modules.character.agent.state import CreationContext, CreationState
from app.modules.character.classes import CLASSES
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
    GearItem,
    PointBuy,
    Race,
    RaceName,
    Skill,
    Weapon,
)
from app.modules.content.schemas import SeedCharacter

CREATION_SYSTEM_PROMPT_ID = "character/system/creator"

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


def build_sheet(request: CharacterCreateRequest) -> CharacterSheet:
    # Function-local: `builder` imports this module for its own lookups
    # (`race`, `character_class`), so a module-scope import here would be
    # a cycle.
    from app.modules.character import builder

    return builder.build_sheet(request)


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


def render_seed(seed: SeedCharacter) -> str:
    """Deterministic review text for the campaign's ready-made hero, the
    same shape as `render_sheet` over `SeedCharacter`'s narrower fields."""
    lines = [
        seed.name,
        f"{seed.race} {seed.character_class}",
        "",
        f"Hit points {seed.max_hp}   Armour class {seed.armour_class}",
        "",
        f"Abilities: {_ability_line(seed.abilities.model_dump())}",
        f"Equipment: {', '.join(seed.inventory) or 'none yet'}",
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
    config = RunnableConfig(
        **tracing.langchain_config("creation-turn"), configurable={"thread_id": thread_id}
    )
    result: dict[str, Any] = await agent.ainvoke(
        {"messages": [HumanMessage(content=player_text)]}, config=config, context=context
    )
    messages = result.get("messages", [])
    reply = messages[-1].text if messages and hasattr(messages[-1], "text") else ""
    return CreationTurn(reply=reply, saved=result.get("saved", False))
