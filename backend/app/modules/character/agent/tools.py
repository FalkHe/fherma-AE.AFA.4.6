"""A tool is the model-facing contract plus a thin call into
`character.service` / `builder.py` / `playthrough.service`, which own
every rule. The docstring is what the model reads to decide when and how
to call it; `runtime` is injected by `ToolNode` and hidden from the
model's schema (same seam as `game.agent.tools`).

Every number on the sheet comes from `builder` through these tools --
never from the model's own words (← AC3). The draft lives in graph state:
a writing tool merges into `runtime.state["draft"]` and returns a
`Command`; a reading tool only reads it.
"""

from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime
from langgraph.types import Command

from app.modules.character import builder, service
from app.modules.character.agent.state import CreationContext
from app.modules.character.errors import CharacterBuildError
from app.modules.character.schemas import CharacterCreateRequest, ClassName, RaceName
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CharacterExistsError

_REQUIRED_DRAFT_FIELDS = ("race", "character_class", "name")


def _draft_gaps(draft: dict[str, Any]) -> list[str]:
    return [field for field in _REQUIRED_DRAFT_FIELDS if not draft.get(field)]


def _request_from_draft(draft: dict[str, Any]) -> CharacterCreateRequest:
    """Least effort: an absent `abilities` is filled from
    `builder.suggested_scores` for the draft's own class, never asked of
    the model."""
    abilities = draft.get("abilities")
    if abilities is None:
        abilities = builder.suggested_scores(draft["character_class"]).model_dump()
    return CharacterCreateRequest(
        name=draft.get("name", ""),
        race=draft["race"],
        character_class=draft["character_class"],
        alignment="Neutral",
        abilities=abilities,
        free_ability_bonuses=[],
        skills=[],
        equipment_picks=[],
        appearance=draft.get("appearance", ""),
        backstory=draft.get("backstory", ""),
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
    race: RaceName, character_class: ClassName, runtime: ToolRuntime[CreationContext]
) -> Command:
    """Write down the player's race and class. Call this only after the
    player has said yes to both -- never before agreement."""
    draft = {**runtime.state.get("draft", {}), "race": race, "character_class": character_class}
    return Command(
        update={
            "draft": draft,
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
    draft = dict(runtime.state.get("draft", {}))
    draft["name"] = name
    if appearance:
        draft["appearance"] = appearance
    if backstory:
        draft["backstory"] = backstory
    return Command(
        update={
            "draft": draft,
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
    new_draft = {**draft, "abilities": abilities.model_dump()}
    summary = ", ".join(f"{ability} {value}" for ability, value in abilities.model_dump().items())
    return Command(
        update={
            "draft": new_draft,
            "messages": [
                ToolMessage(
                    content=f"Suggested scores: {summary}.", tool_call_id=runtime.tool_call_id
                )
            ],
        }
    )


@tool("show_sheet")
def show_sheet(runtime: ToolRuntime[CreationContext]) -> str:
    """Render the full sheet built so far for the player's review. Never
    restate its numbers yourself -- this tool is the only source of them."""
    draft = runtime.state.get("draft", {})
    gaps = _draft_gaps(draft)
    if gaps:
        return "Still missing before I can show a sheet: " + ", ".join(gaps) + "."
    request = _request_from_draft(draft)
    try:
        sheet = service.build_sheet(request)
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
            sheet = service.build_sheet(request)
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
    show_sheet,
    save_character,
]
