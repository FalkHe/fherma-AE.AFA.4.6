"""`app srd status` and `app srd ingest` -- sprint 004-01 WI3
(`status`, binding interface in
`docs/intents/004-srd-knowledge-base/sprints/01-empty-corpus-status/plan.md`,
I3) and sprint 004-02 WI3 (`ingest`).

Thin CLI over `srd/service.py` (WI2). `status` opens its own DB session via
`app.core.db.get_sessionmaker` -- the same helper FastAPI's
`get_db_session` wraps -- because there is no request scope to hang a
`Depends(...)` off in a Typer command (no existing CLI command opens a
`DbSession` yet, so this follows the sessionmaker directly, per
`core/checkpointer/commands.py`'s precedent of running async work through
`asyncio.run(...)`).

`ingest` is synchronous and opens no DB session at all: `--dry-run` is
fetch + store + chunk + report (`IngestReport`) only, and the bare command
(no `--dry-run`) fails before touching `srd_service` -- the real, DB-backed
ingest is a later sprint. Building the dry-run output through `IngestReport`
rather than printing ad hoc keeps that later sprint's report shape ready to
reuse.

Failure is one line to stderr plus `typer.Exit(code=1)`, per
`modules/content/commands.py` / `core/llm/commands.py`. `SrdVectorWidthError`
and `SrdSourceError` carry their own full message, so each is echoed as-is.
The empty-corpus case is not an exception -- `corpus_status` returns
`rule_count == 0` -- so the CLI spells out "0 rules" and the ingest command
itself (decided wording, sprint plan)."""

import asyncio

import typer

from app.core.db import get_sessionmaker
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdSourceError, SrdVectorWidthError
from app.modules.srd.schemas import CorpusStatus, IngestReport

srd_app = typer.Typer()

EMPTY_CORPUS_MESSAGE = "SRD corpus is empty: 0 rules ingested; run `app srd ingest` to load it."
EMBEDDING_NOT_LANDED_MESSAGE = (
    "embedding is not landed yet; run `app srd ingest --dry-run` to preview a fetch instead."
)
_HEADING_SAMPLE_SIZE = 5


async def _fetch_status() -> CorpusStatus:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        return await srd_service.corpus_status(db)


@srd_app.command("status")
def status() -> None:
    try:
        result = asyncio.run(_fetch_status())
    except SrdVectorWidthError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    if result.rule_count == 0:
        typer.echo(EMPTY_CORPUS_MESSAGE, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"rules: {result.rule_count}")
    typer.echo(f"embedding model: {result.embedding_model}")
    typer.echo(f"ingested at: {result.ingested_at}")


@srd_app.command("ingest")
def ingest(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    if not dry_run:
        typer.echo(EMBEDDING_NOT_LANDED_MESSAGE, err=True)
        raise typer.Exit(code=1)

    try:
        path = srd_service.fetch_source()
        chunks = srd_service.chunk_source(path)
    except SrdSourceError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    report = IngestReport(
        source_version=srd_service.SOURCE_VERSION,
        source_bytes=path.stat().st_size,
        chunk_count=len(chunks),
        token_count=sum(chunk.token_count for chunk in chunks),
    )
    heading_sample = list(dict.fromkeys(chunk.heading_path for chunk in chunks))[
        :_HEADING_SAMPLE_SIZE
    ]

    typer.echo(f"stored at: {path}")
    typer.echo(f"bytes: {report.source_bytes}")
    typer.echo(f"chunks: {report.chunk_count}")
    typer.echo(f"tokens: {report.token_count}")
    typer.echo(f"sample headings: {', '.join(heading_sample)}")
