"""Interactive CLI session against a real run. Reply on stdout, rolls on stderr.
Maintains a persistent thread_id across turns within the session backed by the
checkpointer.
"""

import asyncio
import uuid

import typer

from app.core.checkpointer import service as checkpointer_service
from app.core.db import get_sessionmaker
from app.core.llm.errors import LlmError
from app.modules.game import service as game_service
from app.modules.game.agent.state import DmContext
from app.modules.playthrough.errors import PlaythroughError

game_app = typer.Typer()


async def _run_turn(
    agent,
    *,
    user_id: str,
    actor_id: str | None,
    run_id: str | None,
    thread_id: str,
    text: str,
) -> game_service.TurnResult:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        context = DmContext(
            db=db,
            user_id=user_id,
            actor_id=actor_id,
            run_id=run_id,
            turn_id=str(uuid.uuid4()),
        )
        return await game_service.turn(
            agent, thread_id=thread_id, context=context, player_text=text
        )


async def _play_session(
    *,
    user_id: str,
    run_id: str | None,
    actor_id: str | None,
    thread_id: str,
) -> None:
    async with checkpointer_service.checkpointer() as saver:
        agent = game_service.build_agent(checkpointer=saver)
        while True:
            try:
                player_text = await asyncio.to_thread(input, "> ")
            except (EOFError, KeyboardInterrupt):
                break

            if not player_text.strip() or player_text.strip().lower() in (
                ":quit",
                ":q",
                "exit",
                "quit",
            ):
                break

            result = await _run_turn(
                agent,
                user_id=user_id,
                actor_id=actor_id,
                run_id=run_id,
                thread_id=thread_id,
                text=player_text,
            )

            for roll in result.rolls:
                typer.echo(
                    f"rolled {roll['kind']} {roll['formula']}: {roll['faces']} "
                    f"{roll['modifier']:+d} = {roll['total']}",
                    err=True,
                )
            typer.echo(result.reply)


@game_app.command("play")
def play(
    user_id: str = typer.Option(..., "--user", help="The caller's user id."),
    run_id: str | None = typer.Option(None, "--run-id", help="The campaign run id."),
    actor_id: str | None = typer.Option(
        None, "--actor", "--actor-id", help="Optional default actor id override."
    ),
    thread_id: str | None = typer.Option(None, "--thread-id", help="Checkpointer thread id."),
) -> None:
    active_thread_id = thread_id or str(uuid.uuid4())
    try:
        asyncio.run(
            _play_session(
                user_id=user_id,
                run_id=run_id,
                actor_id=actor_id,
                thread_id=active_thread_id,
            )
        )
    except (LlmError, PlaythroughError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
