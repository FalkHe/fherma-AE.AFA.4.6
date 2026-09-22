"""A tool is the model-facing contract plus a thin call into
`character.service` / `builder.py` / `playthrough.service`, which own
every rule. The docstring is what the model reads to decide when and how
to call it; `runtime` is injected by `ToolNode` and hidden from the
model's schema (same seam as `game.agent.tools`).

Every number on the sheet comes from `builder` through these tools --
never from the model's own words (← AC3). The draft lives in graph state
behind `CreationState.draft`'s merge reducer: a writing tool returns only
its own delta in a `Command`, never the full merged dict -- two
draft-writing tool calls can land in the same model step, and merging
locally here would drop whichever ran second. A reading tool only reads
the already-merged `runtime.state["draft"]`.
"""

from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import Command

from app.modules.character import builder, service
from app.modules.character.agent.state import CreationContext
from app.modules.character.errors import CharacterBuildError
from app.modules.character.schemas import (
    AlignmentName,
    CharacterClass,
    CharacterCreateRequest,
    ClassName,
    RaceName,
    SkillName,
)
from app.modules.content.schemas import Abilities
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CharacterExistsError

_REQUIRED_DRAFT_FIELDS = ("race", "character_class", "name")

# Duplicated in `character.service` (own private copy for its own render
# lines) -- a six-entry mapping, not worth a `core/` promotion (same call
# as `builder.py`'s / `service.py`'s own duplicated `_ABILITY_ORDER`).
_ABILITY_ABBR = {
    "strength": "STR",
    "dexterity": "DEX",
    "constitution": "CON",
    "intelligence": "INT",
    "wisdom": "WIS",
    "charisma": "CHA",
}


def _draft_gaps(draft: dict[str, Any]) -> list[str]:
    return [field for field in _REQUIRED_DRAFT_FIELDS if not draft.get(field)]


def _request_from_draft(draft: dict[str, Any]) -> CharacterCreateRequest:
    """Least effort: an absent `abilities` is filled from
    `builder.suggested_scores` for the draft's own class, never asked of
    the model."""
    abilities = draft.get("abilities")
    if abilities is None:
        abilities = builder.suggested_scores(draft["character_class"]).model_dump()
    character_class = service.character_class(draft["character_class"])
    return CharacterCreateRequest(
        name=draft.get("name", ""),
        race=draft["race"],
        character_class=draft["character_class"],
        alignment=draft.get("alignment", "Neutral"),
        abilities=abilities,
        free_ability_bonuses=[],
        skills=draft.get("skills", []),
        equipment_picks=[
            draft.get(f"equipment_pick_{i}", 0) for i in range(len(character_class.equipment))
        ],
        appearance=draft.get("appearance", ""),
        backstory=draft.get("backstory", ""),
    )


def _class_from_draft(draft: dict[str, Any]) -> CharacterClass:
    character_class = draft.get("character_class")
    if character_class is None:
        raise ValueError("Choose a race and class before equipment.")
    return service.character_class(character_class)


@tool("list_options")
def list_options() -> str:
    """List every race and class the player may pick from: the nine SRD
    races and twelve SRD classes, one short line each. Offer this when the
    player asks to see all of them."""
    lines = ["Races:"]
    for race in service.races():
        bonuses = ", ".join(
            f"{ability} +{bonus}" for ability, bonus in race.ability_bonuses.items()
        )
        if race.free_ability_bonuses:
            bonuses = f"{bonuses}, +{race.free_ability_bonuses} free" if bonuses else "free bonuses"
        lines.append(f"- {race.name}: {race.size}, speed {race.speed} ft, {bonuses}")
    lines.append("Classes:")
    for character_class in service.classes():
        saves = ", ".join(character_class.saving_throws)
        lines.append(f"- {character_class.name}: hit die d{character_class.hit_die}, saves {saves}")
    return "\n".join(lines)


@tool("set_race_and_class")
def set_race_and_class(
    race: RaceName, character_class: ClassName, runtime: ToolRuntime[CreationContext]
) -> Command:
    """Write down the player's race and class. Call this only after the
    player has said yes to both -- never before agreement."""
    return Command(
        update={
            "draft": {"race": race, "character_class": character_class},
            "messages": [
                ToolMessage(
                    content=f"Race set to {race}, class set to {character_class}.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool("set_identity")
def set_identity(
    name: str,
    runtime: ToolRuntime[CreationContext],
    appearance: str = "",
    backstory: str = "",
) -> Command:
    """Write down the character's name, and looks and backstory once the
    player has told you. Leave `appearance`/`backstory` empty to leave
    what is already written down untouched -- call again as the player
    fills in what was missing."""
    delta: dict[str, Any] = {"name": name}
    if appearance:
        delta["appearance"] = appearance
    if backstory:
        delta["backstory"] = backstory
    return Command(
        update={
            "draft": delta,
            "messages": [
                ToolMessage(
                    content=f"Identity written down for {name}.", tool_call_id=runtime.tool_call_id
                )
            ],
        }
    )


@tool("suggest_scores")
def suggest_scores(runtime: ToolRuntime[CreationContext]) -> Command:
    """Suggest a point-buy ability score set fitting the class already
    written down in the draft. The class is read from the draft, never
    from your own words -- choose race and class first."""
    draft = runtime.state.get("draft", {})
    character_class = draft.get("character_class")
    if character_class is None:
        raise ValueError("Choose a race and class before suggesting ability scores.")
    abilities = builder.suggested_scores(character_class)
    summary = ", ".join(f"{ability} {value}" for ability, value in abilities.model_dump().items())
    return Command(
        update={
            "draft": {"abilities": abilities.model_dump(), "rolled": False},
            "messages": [
                ToolMessage(
                    content=f"Suggested scores: {summary}.", tool_call_id=runtime.tool_call_id
                )
            ],
        }
    )


@tool("roll_scores")
def roll_scores(runtime: ToolRuntime[CreationContext]) -> Command:
    """Roll the character's six ability scores through the game's own
    dice -- never a number you make up yourself. Calling this again
    re-rolls; the newest roll replaces whatever was rolled before."""
    abilities = builder.roll_scores()
    summary = ", ".join(f"{ability} {value}" for ability, value in abilities.model_dump().items())
    return Command(
        update={
            "draft": {"abilities": abilities.model_dump(), "rolled": True},
            "messages": [
                ToolMessage(content=f"Rolled scores: {summary}.", tool_call_id=runtime.tool_call_id)
            ],
        }
    )


@tool("set_scores")
def set_scores(
    strength: int,
    dexterity: int,
    constitution: int,
    intelligence: int,
    wisdom: int,
    charisma: int,
    runtime: ToolRuntime[CreationContext],
) -> Command:
    """Write down the six ability scores the player chose to spend by
    hand: 27 points across all six, each score 8-15. Always writes, even
    when the spread is not legal yet -- relay the returned message
    verbatim, points left and any problem included; never compute the
    numbers yourself."""
    abilities = Abilities.model_validate(
        {
            "strength": strength,
            "dexterity": dexterity,
            "constitution": constitution,
            "intelligence": intelligence,
            "wisdom": wisdom,
            "charisma": charisma,
        }
    )
    summary = ", ".join(
        f"{_ABILITY_ABBR[ability]} {value}" for ability, value in abilities.model_dump().items()
    )
    points_left = service.point_buy().budget - builder.point_buy_cost(abilities)
    problems = builder.validate_point_buy(abilities)
    message = f"Scores written down: {summary}. Points left: {points_left}."
    if problems:
        message = f"{message} " + "; ".join(problems)
    return Command(
        update={
            "draft": {"abilities": abilities.model_dump(), "rolled": False},
            "messages": [ToolMessage(content=message, tool_call_id=runtime.tool_call_id)],
        }
    )


@tool("set_skills")
def set_skills(
    first: SkillName, second: SkillName, runtime: ToolRuntime[CreationContext]
) -> Command:
    """Write down the two skill proficiencies chosen from the story (the
    class's own skills are filled in on their own -- never ask for
    those)."""
    return Command(
        update={
            "draft": {"skills": [first, second]},
            "messages": [
                ToolMessage(
                    content=f"Skills written down: {first}, {second}.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool("set_alignment")
def set_alignment(alignment: AlignmentName, runtime: ToolRuntime[CreationContext]) -> Command:
    """Write down the chosen alignment, one of the nine SRD alignments."""
    return Command(
        update={
            "draft": {"alignment": alignment},
            "messages": [
                ToolMessage(
                    content=f"Alignment set to {alignment}.", tool_call_id=runtime.tool_call_id
                )
            ],
        }
    )


@tool("list_equipment_choices")
def list_equipment_choices(runtime: ToolRuntime[CreationContext]) -> str:
    """List the class's either/or starting equipment choices, one line
    per choice, numbered from 1, each option already labelled (a), (b),
    ... -- choose a race and class first."""
    draft = runtime.state.get("draft", {})
    character_class = _class_from_draft(draft)
    lines = []
    for index, choice in enumerate(character_class.equipment):
        options = " | ".join(option.label for option in choice.options)
        lines.append(f"{index + 1}. {options}")
    return "\n".join(lines)


@tool("pick_equipment")
def pick_equipment(
    choice_number: int, option_number: int, runtime: ToolRuntime[CreationContext]
) -> Command:
    """Write down one equipment choice by its 1-based numbers from
    `list_equipment_choices` -- `choice_number` picks the line,
    `option_number` picks the (a)/(b)/... option on it. Refuses instead of
    writing when either number is out of range."""
    draft = runtime.state.get("draft", {})
    character_class = _class_from_draft(draft)

    if not (1 <= choice_number <= len(character_class.equipment)):
        content = (
            f"There is no equipment choice {choice_number} -- pick from 1 "
            f"to {len(character_class.equipment)}."
        )
        return Command(
            update={"messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)]}
        )

    choice = character_class.equipment[choice_number - 1]
    if not (1 <= option_number <= len(choice.options)):
        content = (
            f"Choice {choice_number} has no option {option_number} -- "
            f"pick from 1 to {len(choice.options)}."
        )
        return Command(
            update={"messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)]}
        )

    option = choice.options[option_number - 1]
    return Command(
        update={
            "draft": {f"equipment_pick_{choice_number - 1}": option_number - 1},
            "messages": [
                ToolMessage(
                    content=f"Equipment choice {choice_number} written down: {option.label}.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool("take_default_equipment")
def take_default_equipment(runtime: ToolRuntime[CreationContext]) -> Command:
    """Take the class default for every equipment choice still unset --
    an unset choice already resolves to its default option (a), so this
    writes only an `equipment_defaults` marker (← research Decision 3, so
    the sheet-so-far's equipment step can tell it is complete)."""
    draft = runtime.state.get("draft", {})
    character_class = _class_from_draft(draft)
    labels = [
        choice.options[0].label
        for index, choice in enumerate(character_class.equipment)
        if f"equipment_pick_{index}" not in draft
    ]
    content = (
        "Every equipment choice is already made."
        if not labels
        else "Defaults taken: " + ", ".join(labels)
    )
    return Command(
        update={
            "draft": {"equipment_defaults": True},
            "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
        }
    )


@tool("show_sheet")
def show_sheet(runtime: ToolRuntime[CreationContext], ready_made: bool = False) -> str | Command:
    """Render the sheet for the player's review -- never restate its
    numbers yourself, this tool is the only source of them. Pass
    `ready_made=True` to show the campaign's ready-made hero instead of
    the draft being built."""
    if ready_made:
        seed = runtime.context.ready_made
        if seed is None:
            return "There is no ready-made hero offered at this table."
        content = service.render_seed(seed, item_names=runtime.context.ready_made_items)
        # ← research Decision 4: marks the draft so `creation_progress`
        # renders the seed's own review once this turn's collector has
        # printed `content` verbatim (`service.turn`'s `ToolMessage`
        # collection, which this must stay to feed).
        return Command(
            update={
                "draft": {"ready_made": True},
                "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)],
            }
        )

    draft = runtime.state.get("draft", {})
    gaps = _draft_gaps(draft)
    if gaps:
        return "Still missing before I can show a sheet: " + ", ".join(gaps) + "."
    request = _request_from_draft(draft)
    try:
        sheet = service.build_sheet(request, point_buy=not draft.get("rolled", False))
    except CharacterBuildError as exc:
        return "The numbers do not add up yet: " + "; ".join(exc.messages)
    return service.render_sheet(sheet)


@tool("save_character")
async def save_character(
    confirmed: bool,
    runtime: ToolRuntime[CreationContext],
    ready_made: bool = False,
) -> str | Command:
    """Write the character to the run -- the only tool that saves
    anything. `confirmed` must be true; ask "Save as they stand? Saving is
    final for this run." and wait for a yes first. `ready_made` is true
    only when the player is taking the campaign's ready-made hero."""
    if not confirmed:
        return "Nothing saved yet -- say the word when you are ready."

    ctx = runtime.context
    draft = runtime.state.get("draft", {})

    if not ready_made:
        gaps = _draft_gaps(draft)
        if gaps:
            return "Still missing before I can save: " + ", ".join(gaps) + "."

    try:
        if ready_made:
            await playthrough_service.create_character(
                ctx.db, user_id=ctx.user_id, run_id=ctx.run_id, sheet=None
            )
        else:
            request = _request_from_draft(draft)
            sheet = service.build_sheet(request, point_buy=not draft.get("rolled", False))
            await playthrough_service.create_character(
                ctx.db, user_id=ctx.user_id, run_id=ctx.run_id, sheet=sheet
            )
    except CharacterBuildError as exc:
        return "The numbers do not add up yet: " + "; ".join(exc.messages)
    except CharacterExistsError:
        return "You already have a hero at this table -- there is nothing left for me to write."

    return Command(
        update={
            "saved": True,
            "messages": [
                ToolMessage(content="Character saved.", tool_call_id=runtime.tool_call_id)
            ],
        }
    )


TOOLS = [
    list_options,
    set_race_and_class,
    set_identity,
    suggest_scores,
    roll_scores,
    set_scores,
    set_skills,
    set_alignment,
    list_equipment_choices,
    pick_equipment,
    take_default_equipment,
    show_sheet,
    save_character,
]
