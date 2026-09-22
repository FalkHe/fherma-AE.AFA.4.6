"""`app character options` -- sprint 009-01 WI3. `app character create` --
sprint 009-03 WI2.

`options` is a thin CLI over `character/service.py`'s read-only lookups.
Unlike `srd`/`content` there is no session and no I/O here -- the lookups
are pure Python data, so this command always exits 0.

`create` is the interactive terminal chat with the creation agent
(`character/agent`, WI1), modelled on `app game play`
(`game/commands.py`): one session at startup to load the run and its
campaign, then one session per turn while the conversation lasts. Unlike
`game play` it opens no Postgres checkpointer -- `build_creation_agent`
defaults to an in-memory one, so the thread dies with the process and a
quit keeps nothing (← D12)."""

import asyncio
import uuid

import typer

from app.core.db import get_sessionmaker
from app.core.llm.errors import LlmError
from app.modules.character import service as character_service
from app.modules.character.agent.state import CreationContext
from app.modules.character.schemas import CharacterClass, Race
from app.modules.content import service as content_service
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import PlaythroughError

character_app = typer.Typer()

MODEL_ERROR_REPLY = "The tavern is noisy, I did not catch that. Say it again?"
FINALITY_LINE = "Written in the ledger. This one is final for this run."
_FAREWELL = "Suit yourself -- the stool's still warm if you change your mind."
_QUIT_WORDS = {"quit", "exit", ":q", ""}


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


async def _load_greeting(*, user_id: str, run_id: str):
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        run = await playthrough_service.get_campaign_run(db, user_id=user_id, run_id=run_id)
        loaded = content_service.load_campaign(run.campaign_id, run.content_version)
    return loaded.campaign.title, loaded.campaign.seed_character


async def _play_turn(agent, *, thread_id, user_id, run_id, seed, text):
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        context = CreationContext(db=db, user_id=user_id, run_id=run_id, ready_made=seed)
        return await character_service.turn(
            agent, thread_id=thread_id, context=context, player_text=text
        )


async def _create_session(*, user_id: str, run_id: str) -> None:
    campaign_title, seed = await _load_greeting(user_id=user_id, run_id=run_id)
    typer.echo(character_service.render_greeting(campaign_title, seed))

    agent = character_service.build_creation_agent()
    thread_id = str(uuid.uuid4())

    while True:
        try:
            line = await asyncio.to_thread(input, "> ")
        except (EOFError, KeyboardInterrupt):
            typer.echo(_FAREWELL)
            return

        stripped = line.strip()
        if stripped.lower() in _QUIT_WORDS:
            typer.echo(_FAREWELL)
            return

        try:
            result = await _play_turn(
                agent,
                thread_id=thread_id,
                user_id=user_id,
                run_id=run_id,
                seed=seed,
                text=stripped,
            )
        except LlmError:
            typer.echo(MODEL_ERROR_REPLY)
            continue

        typer.echo(result.reply)
        if result.saved:
            typer.echo(FINALITY_LINE)
            return


@character_app.command("create")
def create(
    run_id: str = typer.Option(..., "--run", help="The campaign run id."),
    user_id: str = typer.Option(..., "--user", help="The caller's user id."),
) -> None:
    """Open the terminal creation chat for one campaign run."""
    try:
        asyncio.run(_create_session(user_id=user_id, run_id=run_id))
    except (LlmError, PlaythroughError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
