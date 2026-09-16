"""`app srd status` and `app srd ingest` -- sprint 004-01 WI3
(`status`, binding interface in
`docs/intents/004-srd-knowledge-base/sprints/01-empty-corpus-status/plan.md`,
I3), sprint 004-02 WI3 (`ingest --dry-run`) and sprint 004-03 WI2 (`ingest`'s
real, DB-backed path).

Thin CLI over `srd/service.py`. `status` opens its own DB session via
`app.core.db.get_sessionmaker` -- the same helper FastAPI's
`get_db_session` wraps -- because there is no request scope to hang a
`Depends(...)` off in a Typer command (no existing CLI command opens a
`DbSession` yet, so this follows the sessionmaker directly, per
`core/checkpointer/commands.py`'s precedent of running async work through
`asyncio.run(...)`). `ingest`'s real path follows the same pattern.

`ingest --dry-run` stays exactly as it was: fetch + store + chunk + report
(`IngestReport`), no DB session opened at all. The bare command now runs
`srd_service.ingest` for real: one progress line per batch, printed from the
`on_batch` callback the service fires after each embed batch completes (the
service itself never prints), then the full report -- source version,
bytes, chunk count, token count and cost.

Failure is one line to stderr plus `typer.Exit(code=1)`, per
`modules/content/commands.py` / `core/llm/commands.py`. `SrdError` subclasses
(`SrdVectorWidthError`, `SrdSourceError`, ...) carry their own full message,
so each is echoed as-is. `LlmError` -- a gateway failure partway through
embedding -- carries only the generic, non-provider-specific
`LLM_FAILURE_MESSAGE` in `str(exc)` (← D2); the domain code is appended in
brackets, same idiom as `core/prompts/commands.py`'s `[{exc.code}]`, so the
operator (and a test) can tell which of the seam's eight failure classes
fired without the provider detail ever reaching the terminal. The empty-
corpus case is not an exception -- `corpus_status` returns `rule_count ==
0` -- so the CLI spells out "0 rules" and the ingest command itself
(decided wording, sprint plan)."""

import asyncio

import typer

from app.core.db import get_sessionmaker
from app.core.errors import ErrorCode
from app.core.llm.errors import LlmError
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdError, SrdSourceError, SrdVectorWidthError
from app.modules.srd.schemas import CorpusStatus, IngestReport

srd_app = typer.Typer()

EMPTY_CORPUS_MESSAGE = "SRD corpus is empty: 0 rules ingested; run `app srd ingest` to load it."
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


def _cost_line(report: IngestReport) -> str:
    """Renders `IngestReport.cost_usd` per the decided three cases: a full
    total when every priced batch is in hand, a labelled lower bound when
    the gateway only priced some batches (`cost_complete is False`), and an
    explicit "unavailable" when nothing was priced at all (`cost_usd is
    None`)."""
    if report.cost_usd is None:
        return "cost: unavailable (the gateway priced no batch)"
    if report.cost_complete:
        return f"cost: ${report.cost_usd:.6f} (total)"
    return (
        f"cost: at least ${report.cost_usd:.6f} "
        "(incomplete -- the gateway priced only some batches)"
    )


def _llm_error_line(exc: LlmError) -> str:
    """One stderr line for a gateway failure: the generic, non-provider
    message (← D2, `str(exc)`) plus the domain code in brackets so the
    operator can tell which of the seam's eight failure classes fired,
    same idiom as `core/prompts/commands.py`'s `[{exc.code}]`. `getattr`
    with a default covers `LlmConfigurationError`, which sets no `.code`
    (← `core/errors.py`'s own handler)."""
    code = getattr(exc, "code", ErrorCode.INTERNAL_ERROR)
    return f"{exc} [{code.value}]"


async def _run_ingest() -> IngestReport:
    sessionmaker = get_sessionmaker()

    def _on_batch(chunks_done: int, chunks_total: int) -> None:
        typer.echo(f"embedded {chunks_done}/{chunks_total} chunks")

    async with sessionmaker() as db:
        return await srd_service.ingest(db, on_batch=_on_batch)


@srd_app.command("ingest")
def ingest(dry_run: bool = typer.Option(False, "--dry-run")) -> None:
    if not dry_run:
        try:
            report = asyncio.run(_run_ingest())
        except LlmError as exc:
            typer.echo(_llm_error_line(exc), err=True)
            raise typer.Exit(code=1) from exc
        except SrdError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(f"source version: {report.source_version}")
        typer.echo(f"bytes: {report.source_bytes}")
        typer.echo(f"chunks: {report.chunk_count}")
        typer.echo(f"tokens: {report.token_count}")
        typer.echo(_cost_line(report))
        return

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
