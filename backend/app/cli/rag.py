"""`app rag` — run the whole advanced-RAG pipeline from the command line.

`app rag ask "I'm 1.65m, just got my A2, mostly city commuting"` runs exactly
what the advisor's `retrieve_bike_knowledge` tool will run
(`app.services.rag_pipeline_service.retrieve`) and prints every stage of it: the
translated queries, the spec filters the sentence supported, the candidate
shortlist those filters and any named bike produced, and the fused chunks with
their provenance. It is the harness for judging whether the *plan* is wrong or
the *knowledge base* is thin — `app retrieval search` only shows the latter.

Conventions of `app.cli.retrieval` / `app.cli.chunks`: the Typer command body
stays synchronous and calls `asyncio.run(...)`, the async half opens one session
and only calls services, and an expected failure is a message on stderr with
exit code 1 instead of a traceback.
"""

import asyncio
from typing import Annotated, NoReturn

import typer

from app.db.session import get_sessionmaker
from app.llm.models import MissingApiKeyError
from app.services import product_service, rag_pipeline_service, retrieval_service

app = typer.Typer(
    help="Run the retrieval pipeline the advisor uses.",
    no_args_is_help=True,
    add_completion=False,
)

# How much of a chunk one result line shows (as in `app retrieval search`).
EXCERPT_CHARS = 240
# How many candidate bikes are named before the list is summarised: a filter set
# can legitimately match the whole catalogue.
CANDIDATE_PREVIEW = 12


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("ask")
def ask(
    utterance: Annotated[str, typer.Argument(help="What the customer said, verbatim.")],
    summary: Annotated[
        str,
        typer.Option("--summary", help="A recap of the conversation so far, for the translation."),
    ] = "",
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=100, help="How many fused chunks to print."),
    ] = retrieval_service.DEFAULT_LIMIT,
) -> None:
    """Translate one utterance, narrow the catalogue, retrieve and print.

    Prints the four parts of the result in the order the pipeline produced them:
    queries, applied filters, candidate bikes, fused chunks.
    """
    try:
        result, candidate_names = asyncio.run(_ask(utterance, summary, limit))
    except retrieval_service.StaleEmbeddingsError as error:
        _fail(str(error))
    except MissingApiKeyError as error:
        _fail(f"{error} Translation and retrieval both need it. Set it in .env and retry.")

    _print_plan(result, candidate_names)

    if not result.chunks:
        typer.echo("No matching chunks.", err=True)
        return

    typer.echo(f"chunks ({len(result.chunks)}, fused across {len(result.queries)} query/queries):")
    for rank, chunk in enumerate(result.chunks, start=1):
        _print_chunk(rank, chunk)


async def _ask(
    utterance: str, summary: str, limit: int
) -> tuple[rag_pipeline_service.RagResult, dict[str, str]]:
    """Async half of `ask`: one session, the pipeline, then the display names."""
    async with get_sessionmaker()() as session:
        result = await rag_pipeline_service.retrieve(
            session, utterance, history_summary=summary, limit=limit
        )
        names: dict[str, str] = {}
        for motorbike_id in result.candidate_motorbike_ids[:CANDIDATE_PREVIEW]:
            motorbike = await product_service.get_motorbike(session, motorbike_id)
            if motorbike is not None:
                names[motorbike_id] = motorbike.query_name
        return result, names


def _print_plan(result: rag_pipeline_service.RagResult, candidate_names: dict[str, str]) -> None:
    """Print the plan: what was searched, under which filters, over which bikes."""
    typer.echo("queries:")
    for query in result.queries:
        typer.echo(f"  - {query}")

    typer.echo("filters:")
    if not result.applied_filters:
        typer.echo("  (none derived — the whole approved catalogue)")
    for field, value in result.applied_filters.items():
        typer.echo(f"  - {field}: {value}")

    candidates = result.candidate_motorbike_ids
    typer.echo(f"candidates ({len(candidates)}):")
    if not candidates:
        typer.echo(
            "  (no shortlist — filters matched nothing)"
            if result.applied_filters
            else "  (unscoped — nothing to narrow with)"
        )
    for motorbike_id in candidates[:CANDIDATE_PREVIEW]:
        typer.echo(f"  - {candidate_names.get(motorbike_id, '(unknown)')} · {motorbike_id}")
    if len(candidates) > CANDIDATE_PREVIEW:
        typer.echo(f"  … and {len(candidates) - CANDIDATE_PREVIEW} more")


def _print_chunk(rank: int, chunk: retrieval_service.RetrievedChunk) -> None:
    """Print one fused result: score first, then where it came from, then text."""
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
