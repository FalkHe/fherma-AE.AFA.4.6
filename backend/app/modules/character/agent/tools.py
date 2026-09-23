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


def _describe_gaps(gaps: list[str]) -> str:
    names = {"race": "race", "character_class": "class", "name": "name"}
    return ", ".join(names[gap] for gap in gaps)


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


def _class_from_draft(draft: dict[str, Any]) -> CharacterClass | None:
    character_class = draft.get("character_class")
    if character_class is None:
        return None
    return service.character_class(character_class)


_CLASS_NEEDED = (
    "I need your class written in the ledger before I can lay out your gear. "
    "Tell me which class you choose, then confirm it."
)
_READY_MADE_CHANGE = (
    "That ready-made hero is already equipped as written. To change them, "
    "choose a race and class for a new hero first; then I can write your changes."
)


def _editing_ready_made(draft: dict[str, Any]) -> bool:
    return bool(draft.get("ready_made") and not draft.get("character_class"))


def _explain(runtime: ToolRuntime[CreationContext], content: str) -> Command:
    """Make a prerequisite or refusal visible even if the model misses it."""
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=runtime.tool_call_id,
                    additional_kwargs={"show_player": True, "refusal": True},
                )
            ]
        }
    )


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
    runtime: ToolRuntime[CreationContext],
    race: RaceName | None = None,
    character_class: ClassName | None = None,
) -> Command | str:
    """Write down a confirmed race or class choice. On a correction, pass
    only the field the player changed; the other stays as recorded. Never
    write an initial choice before the player agrees to it."""
    draft = runtime.state.get("draft", {})
    if race is None and character_class is None:
        return _explain(runtime, "Tell me which race or class you would like written down.")
    delta: dict[str, Any] = {}
    if race is not None:
        delta["race"] = race
    if character_class is not None:
        delta["character_class"] = character_class
    if character_class is not None and draft.get("character_class") != character_class:
        delta.update({key: None for key in draft if key.startswith("equipment_pick_")})
        delta["equipment_defaults"] = None
    delta["ready_made"] = None
    chosen_race = race or draft.get("race")
    chosen_class = character_class or draft.get("character_class")
    written = ", ".join(
        f"your {label} as {value}"
        for label, value in (("race", race), ("class", character_class))
        if value is not None
    )
    written = f"I've written {written}"
    missing = []
    if chosen_race is None:
        missing.append("race")
    if chosen_class is None:
        missing.append("class")
    if missing:
        written += f". I still need your {' and '.join(missing)} before the sheet is complete"
    return Command(
        update={
            "draft": delta,
            "messages": [
                ToolMessage(
                    content=f"{written}.",
                    tool_call_id=runtime.tool_call_id,
                    additional_kwargs={"show_player": bool(missing)},
                )
            ],
        }
    )


@tool("set_identity")
def set_identity(
    runtime: ToolRuntime[CreationContext],
    name: str | None = None,
    appearance: str | None = None,
    backstory: str | None = None,
) -> Command | str:
    """Write a confirmed name, appearance or backstory. Pass only the
    fields the player changed; omitted fields stay as written. An empty
    appearance or backstory clears that field."""
    if _editing_ready_made(runtime.state.get("draft", {})):
        return _explain(runtime, _READY_MADE_CHANGE)
    delta: dict[str, Any] = {}
    if name is not None:
        if not name.strip():
            return _explain(runtime, "A hero needs a name. Tell me what I should write.")
        delta["name"] = name
    if appearance is not None:
        delta["appearance"] = appearance
    if backstory is not None:
        delta["backstory"] = backstory
    if not delta:
        return _explain(runtime, "Tell me which name, look or story detail you would like changed.")
    current_name = runtime.state.get("draft", {}).get("name")
    return Command(
        update={
            "draft": delta,
            "messages": [
                ToolMessage(
                    content=f"Identity written down for {name or current_name or 'your hero'}.",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )


@tool("suggest_scores")
def suggest_scores(runtime: ToolRuntime[CreationContext]) -> Command | str:
    """Suggest a point-buy ability score set fitting the class already
    written down in the draft. The class is read from the draft, never
    from your own words -- choose a class first."""
    draft = runtime.state.get("draft", {})
    if _editing_ready_made(draft):
        return _explain(runtime, _READY_MADE_CHANGE)
    character_class = draft.get("character_class")
    if character_class is None:
        return _explain(
            runtime,
            "I need your class written in the ledger before I can suggest scores. "
            "Choose a class, then confirm it.",
        )
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
def roll_scores(runtime: ToolRuntime[CreationContext]) -> Command | str:
    """Roll the character's six ability scores through the game's own
    dice -- never a number you make up yourself. Calling this again
    re-rolls; the newest roll replaces whatever was rolled before."""
    if _editing_ready_made(runtime.state.get("draft", {})):
        return _explain(runtime, _READY_MADE_CHANGE)
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
) -> Command | str:
    """Write down the six ability scores the player chose to spend by
    hand: 27 points across all six, each score 8-15. Always writes, even
    when the spread is not legal yet -- relay the returned message
    verbatim, points left and any problem included; never compute the
    numbers yourself."""
    if _editing_ready_made(runtime.state.get("draft", {})):
        return _explain(runtime, _READY_MADE_CHANGE)
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
    runtime: ToolRuntime[CreationContext],
    first: SkillName | None = None,
    second: SkillName | None = None,
) -> Command | str:
    """Write either or both confirmed story skills. Omitted positions
    keep their previous choice; the class's own skills fill in on their
    own. A single story skill shows in the preview while the second is
    still being chosen."""
    draft = runtime.state.get("draft", {})
    if _editing_ready_made(draft):
        return _explain(runtime, _READY_MADE_CHANGE)
    if first is None and second is None:
        return _explain(runtime, "Tell me which story skill you would like written down.")
    skills = list(draft.get("skills", []))
    if first is not None:
        if skills:
            skills[0] = first
        else:
            skills.append(first)
    if second is not None:
        if not skills:
            return _explain(
                runtime,
                "I can write the second skill once you choose the first. Which comes first?",
            )
        if len(skills) == 1:
            skills.append(second)
        else:
            skills[1] = second
    if len(skills) == 2 and skills[0] == skills[1]:
        return _explain(runtime, "Those are the same skill twice. Choose a different second skill.")
    content = f"I've written down {', '.join(skills)}."
    if len(skills) == 1:
        content += " I still need one more story skill."
    return Command(
        update={
            "draft": {"skills": skills},
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=runtime.tool_call_id,
                    additional_kwargs={"show_player": len(skills) == 1},
                )
            ],
        }
    )


@tool("set_alignment")
def set_alignment(alignment: AlignmentName, runtime: ToolRuntime[CreationContext]) -> Command | str:
    """Write down the chosen alignment, one of the nine SRD alignments."""
    if _editing_ready_made(runtime.state.get("draft", {})):
        return _explain(runtime, _READY_MADE_CHANGE)
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
def list_equipment_choices(runtime: ToolRuntime[CreationContext]) -> str | Command:
    """List the class's either/or starting equipment choices, one line
    per choice, numbered from 1, each option already labelled (a), (b),
    ... -- choose a class first."""
    draft = runtime.state.get("draft", {})
    if _editing_ready_made(draft):
        return _explain(runtime, _READY_MADE_CHANGE)
    character_class = _class_from_draft(draft)
    if character_class is None:
        return _explain(runtime, _CLASS_NEEDED)
    lines = []
    for index, choice in enumerate(character_class.equipment):
        options = " | ".join(option.label for option in choice.options)
        lines.append(f"{index + 1}. {options}")
    return "\n".join(lines)


@tool("pick_equipment")
def pick_equipment(
    choice_number: int, option_number: int, runtime: ToolRuntime[CreationContext]
) -> Command | str:
    """Write down one equipment choice by its 1-based numbers from
    `list_equipment_choices` -- `choice_number` picks the line,
    `option_number` picks the (a)/(b)/... option on it. Refuses instead of
    writing when either number is out of range."""
    draft = runtime.state.get("draft", {})
    if _editing_ready_made(draft):
        return _explain(runtime, _READY_MADE_CHANGE)
    character_class = _class_from_draft(draft)
    if character_class is None:
        return _explain(runtime, _CLASS_NEEDED)

    if not (1 <= choice_number <= len(character_class.equipment)):
        content = (
            f"There is no equipment choice {choice_number} -- pick from 1 "
            f"to {len(character_class.equipment)}."
        )
        return _explain(runtime, content)

    choice = character_class.equipment[choice_number - 1]
    if not (1 <= option_number <= len(choice.options)):
        content = (
            f"Choice {choice_number} has no option {option_number} -- "
            f"pick from 1 to {len(choice.options)}."
        )
        return _explain(runtime, content)

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
def take_default_equipment(runtime: ToolRuntime[CreationContext]) -> Command | str:
    """Take the class default for every equipment choice still unset --
    an unset choice already resolves to its default option (a), so this
    writes only an `equipment_defaults` marker (← research Decision 3, so
    the sheet-so-far's equipment step can tell it is complete)."""
    draft = runtime.state.get("draft", {})
    if _editing_ready_made(draft):
        return _explain(runtime, _READY_MADE_CHANGE)
    character_class = _class_from_draft(draft)
    if character_class is None:
        return _explain(runtime, _CLASS_NEEDED)
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
            return _explain(runtime, "There is no ready-made hero offered at this table.")
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
        return _explain(
            runtime, "I still need your " + _describe_gaps(gaps) + " before I can show the sheet."
        )
    request = _request_from_draft(draft)
    try:
        sheet = service.build_sheet(request, point_buy=not draft.get("rolled", False))
    except CharacterBuildError as exc:
        return _explain(runtime, "The numbers do not add up yet: " + "; ".join(exc.messages))
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
        return "Nothing saved yet. Say the word when you are ready."

    ctx = runtime.context
    draft = runtime.state.get("draft", {})

    if not ready_made:
        gaps = _draft_gaps(draft)
        if gaps:
            return _explain(
                runtime, "I still need your " + _describe_gaps(gaps) + " before I can save."
            )

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
        return _explain(runtime, "The numbers do not add up yet: " + "; ".join(exc.messages))
    except CharacterExistsError:
        return _explain(
            runtime, "You already have a hero at this table. There is nothing left for me to write."
        )

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
