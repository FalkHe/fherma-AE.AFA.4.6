"""`app retrieval` — query the hybrid retriever from the command line.

`app retrieval search "comfortable touring bike"` runs exactly what the advisor
runs (`app.services.retrieval_service.search`) and prints the fused ranking with
its provenance. It is the tuning harness for the retrieval constants (`RRF_K`,
`RETRIEVAL_CANDIDATES_PER_LEG`) and the fastest way to see whether the knowledge
base actually contains what an answer would need — no chat, no agent loop in the
way.

Follows the CLI conventions of `app.cli.chunks` / `app.cli.llm`: the Typer
command body stays synchronous and calls `asyncio.run(...)`, the async half opens
one session and only calls services, and an expected failure is a message on
stderr with exit code 1 instead of a traceback.
"""

import asyncio
from typing import Annotated, NoReturn

import typer

from app.db.session import get_sessionmaker
from app.llm.models import MissingApiKeyError
from app.services import retrieval_service

app = typer.Typer(
    help="Query the hybrid retriever over the chunked knowledge base.",
    no_args_is_help=True,
    add_completion=False,
)

# How much of a chunk one result line shows: enough to judge relevance, short
# enough that ten results still fit on a screen.
EXCERPT_CHARS = 240


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="What to search the knowledge base for.")],
    bike: Annotated[
        str | None,
        typer.Option("--bike", help="Restrict the search to one motorbike id (ULID)."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=100, help="How many fused results to print."),
    ] = retrieval_service.DEFAULT_LIMIT,
) -> None:
    """Search approved models' knowledge base and print the fused ranking.

    Prints one block per result: rank, fused score, source title and heading
    path, the source URL, the chunk's identity and an excerpt of its text.
    """
    try:
        chunks = asyncio.run(_search(query, bike, limit))
    except retrieval_service.StaleEmbeddingsError as error:
        _fail(str(error))
    except MissingApiKeyError as error:
        _fail(f"{error} The query itself has to be embedded. Set it in .env and retry.")

    if not chunks:
        typer.echo("No matching chunks.", err=True)
        return

    typer.echo(f"{len(chunks)} result(s) for {query!r}.", err=True)
    for rank, chunk in enumerate(chunks, start=1):
        _print_chunk(rank, chunk)


async def _search(
    query: str, bike: str | None, limit: int
) -> list[retrieval_service.RetrievedChunk]:
    """Async half of `search`: one session, one service call."""
    async with get_sessionmaker()() as session:
        return await retrieval_service.search(
            session,
            query,
            motorbike_ids=None if bike is None else [bike],
            limit=limit,
        )


def _print_chunk(rank: int, chunk: retrieval_service.RetrievedChunk) -> None:
    """Print one result: the score first, then where it came from, then text."""
    heading = f" — {chunk.heading_path}" if chunk.heading_path else ""
    typer.echo(f"{rank:>2}. {chunk.score:.5f}  {chunk.source_title}{heading}")
    typer.echo(f"    url:   {chunk.source_url or '(no url)'}")
    typer.echo(
        f"    chunk: {chunk.chunk_id} · bike {chunk.motorbike_id} · "
        f"document {chunk.source_document_id} · sequence {chunk.sequence}"
    )
    typer.echo(f"    text:  {_excerpt(chunk.text)}")


def _excerpt(text: str) -> str:
    """Collapse a chunk to one readable line."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= EXCERPT_CHARS:
        return collapsed
    return f"{collapsed[:EXCERPT_CHARS]}…"


def _fail(message: str) -> NoReturn:
    """Report an expected failure on stderr and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
