"""`app character options` -- sprint 009-01 WI3.

Thin CLI over `character/service.py`'s read-only lookups. Unlike
`srd`/`content` there is no session and no I/O here -- the lookups are pure
Python data, so this command always exits 0."""

import typer

from app.modules.character import service as character_service
from app.modules.character.schemas import CharacterClass, Race

character_app = typer.Typer()


def _ability_bonuses(race: Race) -> str:
    parts = [f"{ability} +{bonus}" for ability, bonus in race.ability_bonuses.items()]
    if race.free_ability_bonuses:
        parts.append(f"+{race.free_ability_bonuses} free")
    return ", ".join(parts)


def _print_race(race: Race) -> None:
    typer.echo(f"  {race.name}  speed {race.speed}  {race.size}  {_ability_bonuses(race)}")


def _print_class(character_class: CharacterClass) -> None:
    saves = ", ".join(character_class.saving_throws)
    typer.echo(
        f"  {character_class.name}  hit die d{character_class.hit_die}  "
        f"saves {saves}  skills {character_class.skill_choices} of "
        f"{len(character_class.skill_options)}"
    )
    for choice in character_class.equipment:
        # `EquipmentOption.label` already carries its own "(a)"/"(b)" marker
        # (hand-authored in `classes.py`), so the options are joined as-is.
        line = " | ".join(option.label for option in choice.options)
        typer.echo(f"    {line}")


@character_app.command("options")
def options() -> None:
    races = character_service.races()
    typer.echo(f"races: {len(races)}")
    for race in races:
        _print_race(race)

    classes = character_service.classes()
    typer.echo(f"classes: {len(classes)}")
    for character_class in classes:
        _print_class(character_class)
