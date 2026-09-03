"""`app chunks` — rebuild the retrievable chunks of the knowledge base.

`app chunks rebuild` runs the structural chunker over stored source documents
and replaces their chunks. It runs **in this process**, not as a background job:
splitting is pure CPU on text that is already in the database, so a catalogue of
this size finishes in seconds and there is nothing to report progress about.
Filling the embedding columns is the expensive half, and that is a job of its
own.

Because a rebuild resets the embedding columns, `app chunks rebuild` is also the
command that invalidates embeddings on purpose — run the embedding pass after it.

Follows the CLI async pattern of `app.cli.users`: the Typer command body stays
synchronous and calls `asyncio.run(...)`; the async half opens one session and
only calls services.
"""

import asyncio
from typing import Annotated, NoReturn

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.services import chunking, product_service

app = typer.Typer(
    help="Rebuild the chunked knowledge base.",
    no_args_is_help=True,
    add_completion=False,
)

# One page of catalogue entries per query when rebuilding everything; the
# catalogue ceiling is a few hundred rows, so this is one or two round trips.
PAGE_SIZE = 100


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("rebuild")
def rebuild(
    slug: Annotated[
        str | None,
        typer.Argument(help='Slug of one catalogue entry, e.g. "suzuki-gsr600". Omit for all.'),
    ] = None,
) -> None:
    """Re-chunk every stored document, or only those of one catalogue entry.

    Existing chunks are deleted and written again, so their embeddings are reset
    to NULL. Prints one line per model and a total.
    """
    total = asyncio.run(_rebuild(slug))
    typer.echo(f"Rebuilt {total.chunks} chunk(s) from {total.documents} document(s).")


async def _rebuild(slug: str | None) -> chunking.RebuildSummary:
    """Async half of `rebuild`: one session, one service call per model."""
    async with get_sessionmaker()() as session:
        if slug is not None:
            return await _rebuild_one(session, slug)
        return await _rebuild_all(session)


async def _rebuild_one(session: AsyncSession, slug: str) -> chunking.RebuildSummary:
    """Re-chunk one catalogue entry, reporting an unknown slug as such."""
    motorbike = await product_service.get_by_slug(session, slug)
    if motorbike is None:
        _fail(f"No catalogue entry with slug {slug!r}.")
    return _report(motorbike.slug, await chunking.rebuild_for_motorbike(session, motorbike.id))


async def _rebuild_all(session: AsyncSession) -> chunking.RebuildSummary:
    """Re-chunk the whole catalogue, one page of models at a time."""
    documents = 0
    chunks = 0
    offset = 0
    while True:
        page, total = await product_service.list_motorbikes(session, limit=PAGE_SIZE, offset=offset)
        if not page:
            break
        for motorbike in page:
            summary = _report(
                motorbike.slug, await chunking.rebuild_for_motorbike(session, motorbike.id)
            )
            documents += summary.documents
            chunks += summary.chunks
        offset += len(page)
        if offset >= total:
            break
    return chunking.RebuildSummary(documents=documents, chunks=chunks)


def _report(slug: str, summary: chunking.RebuildSummary) -> chunking.RebuildSummary:
    """Print what one model's rebuild wrote and pass the summary through."""
    typer.echo(
        f"  {slug}: {summary.documents} document(s) → {summary.chunks} chunk(s)",
        err=True,
    )
    return summary


def _fail(message: str) -> NoReturn:
    """Report a bad argument on stderr and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
