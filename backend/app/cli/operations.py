"""`app operations` — drive a fake operation through its lifecycle.

`app operations demo` exists for one reason: it produces the exact sequence of
`operation.updated` events a real ingestion produces, without a network, an LLM
or a worker. That makes it the tool for proving the live progress path —
service → `pg_notify` → SSE → browser — end to end before real ingestion
exists, and afterwards it stays the cheapest way to reproduce the path.

Follows the CLI async pattern of `app.cli.users`: the Typer command body stays
synchronous and calls `asyncio.run(_impl(...))`; the async half opens one
session and only calls services.
"""

import asyncio
from typing import Annotated, NoReturn

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operation import Operation
from app.db.session import get_sessionmaker
from app.services import operation_service, product_service

app = typer.Typer(
    help="Inspect and simulate background operations.",
    no_args_is_help=True,
    add_completion=False,
)

DEMO_TYPE = "demo"

# Seconds between two state changes — long enough to watch a chip move in the
# browser, short enough that the whole run stays a few seconds.
STEP_SECONDS = 1.0

# The pinned ingestion milestones, so the demo looks like the real thing.
DEMO_MILESTONES: tuple[tuple[int, str], ...] = (
    (5, "Looking up Wikipedia"),
    (15, "Searching the web"),
    (40, "Fetching sources (3/6)"),
    (65, "Processing images"),
    (80, "Extracting specifications"),
    (90, "Generating embeddings"),
)


class _UnknownModelError(Exception):
    """Raised when `--bike` names a slug the catalogue does not have."""


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("demo")
def demo(
    bike: Annotated[
        str | None,
        typer.Option("--bike", help="Slug of a catalogue entry to attach the operation to."),
    ] = None,
) -> None:
    """Walk a `demo` operation from queued to succeeded, one step per second.

    Without `--bike` the operation has no entity; with it, the row is linked to
    that motorbike, which is what the admin backlog needs to show progress in
    the model's own row.
    """
    try:
        operation = asyncio.run(_demo(bike))
    except _UnknownModelError as error:
        _fail_unknown_model(str(error), error)

    typer.echo(f"Operation {operation.id} finished as {operation.status.value}.")


async def _demo(slug: str | None) -> Operation:
    """Async half of `demo`: one session, one operation, one lifecycle."""
    async with get_sessionmaker()() as session:
        entity_type, entity_id = await _entity(session, slug)
        operation = await operation_service.create(
            session, DEMO_TYPE, entity_type=entity_type, entity_id=entity_id
        )
        _report(operation)

        await asyncio.sleep(STEP_SECONDS)
        _report(await operation_service.start(session, operation))

        for progress, message in DEMO_MILESTONES:
            await asyncio.sleep(STEP_SECONDS)
            _report(await operation_service.advance(session, operation, progress, message))

        await asyncio.sleep(STEP_SECONDS)
        return await operation_service.succeed(session, operation)


async def _entity(session: AsyncSession, slug: str | None) -> tuple[str | None, str | None]:
    """Resolve `--bike` to the entity pair an operation is linked by.

    Raises:
        _UnknownModelError: the slug is not in the catalogue.
    """
    if slug is None:
        return None, None

    motorbike = await product_service.get_by_slug(session, slug)
    if motorbike is None:
        raise _UnknownModelError(slug)
    return operation_service.MOTORBIKE_ENTITY_TYPE, motorbike.id


def _report(operation: Operation) -> None:
    """Print one state change, so a terminal shows what a listener receives."""
    typer.echo(f"{operation.status.value:>9} {operation.progress:>3}%  {operation.message or ''}")


def _fail_unknown_model(slug: str, error: Exception) -> NoReturn:
    """Report an unknown slug on stderr and exit non-zero."""
    typer.echo(f"No catalogue entry with slug {slug!r}.", err=True)
    raise typer.Exit(code=1) from error


if __name__ == "__main__":  # pragma: no cover
    app()
