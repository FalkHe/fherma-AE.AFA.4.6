"""`app embeddings` — rebuild the vector half of the knowledge base.

`app embeddings rebuild` enqueues the `embeddings.rebuild` job: it re-chunks and
re-embeds **every** stored source document with the configured
`EMBEDDING_MODEL`, which is what makes it the command to run after changing that
model. Unlike `app chunks rebuild` (pure CPU, in this process) the work is
expensive and remote, so it is a tracked background job — the operation row is
created here, before the enqueue, and `GET /api/operations` is where the run is
followed.

Follows the CLI enqueue contract of `app.cli.jobs`: the Typer command body stays
synchronous and calls `asyncio.run(...)`; the async half starts the broker, kicks
the task, shuts the broker down again and waits for nothing.
"""

import asyncio

import typer

from app.db.session import get_sessionmaker
from app.jobs.broker import broker
from app.jobs.embeddings import rebuild as rebuild_task
from app.services import embedding_service, operation_service

app = typer.Typer(
    help="Rebuild the embeddings of the knowledge base.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("rebuild")
def rebuild() -> None:
    """Enqueue a full re-chunk and re-embed of every stored source document.

    Prints the operation id to follow, and returns: the worker does the work.
    """
    operation_id, task_id = asyncio.run(_rebuild())
    typer.echo(f"Task {task_id}.", err=True)
    typer.echo(f"Enqueued {embedding_service.REBUILD_OPERATION_TYPE} as operation {operation_id}.")


async def _rebuild() -> tuple[str, str]:
    """Async half of `rebuild`: the pinned create-then-enqueue sequence.

    The operation row is committed before the task is kicked, so the worker can
    never pick up a job whose state is not yet visible. The broker connection is
    opened and closed around the enqueue, because a one-off CLI process owns the
    Redis connection it opens.
    """
    await broker.startup()
    try:
        async with get_sessionmaker()() as session:
            operation = await operation_service.create(
                session, embedding_service.REBUILD_OPERATION_TYPE
            )
            operation_id = operation.id
        task = await rebuild_task.kiq(operation_id)
        return operation_id, task.task_id
    finally:
        await broker.shutdown()


if __name__ == "__main__":  # pragma: no cover
    app()
