"""`app jobs` — enqueue background jobs from the command line.

Follows the CLI async pattern of `app.cli.users`: the Typer command body stays
synchronous and calls `asyncio.run(_impl(...))`. The async half starts the
broker, kicks the task and shuts the broker down again, because a one-off CLI
process owns the Redis connection it opens.

Nothing here waits for a result: the broker has no result backend and job state
is read from PostgreSQL.
"""

import asyncio
from typing import Annotated

import typer

from app.jobs.broker import broker
from app.jobs.demo import ping as demo_ping

app = typer.Typer(
    help="Enqueue background jobs.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("ping")
def ping(
    message: Annotated[
        str,
        typer.Argument(help="Message the worker should log."),
    ] = "pong",
) -> None:
    """Enqueue `demo.ping`; the worker log proves the queue loop works."""
    task_id = asyncio.run(_ping(message))
    typer.echo(f"Enqueued demo.ping as {task_id}.")


async def _ping(message: str) -> str:
    """Async half of `ping`: one broker connection, one enqueue."""
    await broker.startup()
    try:
        task = await demo_ping.kiq(message)
    finally:
        await broker.shutdown()
    return task.task_id


if __name__ == "__main__":  # pragma: no cover
    app()
