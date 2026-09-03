"""`app seed` — populate the catalogue with a curated demo model list.

`app seed demo` walks `backend/app/cli/data/seed_models.json` (names only —
everything else comes from the pipeline) and, for each name, drives it
through the exact admin ingestion path: `product_service.create_backlog` then
`product_service.start_ingestion` — the same create → transition → enqueue
sequence `POST /api/products` and `app ingest run` use. No bypass, no
shortcut.

A model whose slug already exists in the catalogue, **in any status**, is
skipped: Phase-2b's fresh-run pin means re-ingesting an existing row would
delete its documents and embeddings, so the seed must never touch a model
that is already there.

Ingestion happens in the worker; this command polls the operation row it
created — via an explicit, awaited `session.refresh` (never an expired-
attribute implicit reload) — until it reaches a terminal status or a
per-model timeout elapses. With `--auto-approve` and a `succeeded` run, it
then calls `product_service.transition(in_review -> approved)`, the exact
service every other approval path uses — never a direct status write. Since
step 6.12, that transition also enforces D4 (a complete identity is required
to approve); until extraction (6.15) fills it in, an auto-approve attempt is
reported as `failed`, same as an ingestion failure, rather than crashing the
run.

A model can flake (search quality, fetch timeouts, a slow LLM call): one
failure is reported and the run continues to the next name (report-and-
continue). The command's own exit code is 1 only when every attempted
(non-skipped) model failed.

Follows the CLI async pattern of `app.cli.users`: the Typer command body stays
synchronous and calls `asyncio.run(...)`; the async half owns the session and
the broker connection.
"""

import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.motorbike import MotorbikeStatus
from app.db.models.operation import Operation, OperationStatus
from app.db.session import get_sessionmaker
from app.jobs.broker import broker
from app.services import product_service

app = typer.Typer(
    help="Seed the catalogue with a curated demo model list.",
    no_args_is_help=True,
    add_completion=False,
)

SEED_MODELS_PATH = Path(__file__).parent / "data" / "seed_models.json"

# How often to re-check an in-flight ingestion, and how long to wait before
# giving up on one model. The pipeline's own `SmartRetryMiddleware` already
# retries transient job errors, so no additional retry is layered on top here.
POLL_INTERVAL_SECONDS = 5.0
INGESTION_TIMEOUT_SECONDS = 600.0  # 10 minutes/model


@dataclass(frozen=True)
class _SeedResult:
    """One line of the final summary table."""

    name: str
    outcome: str  # "seeded" | "approved" | "skipped" | "failed"
    detail: str = ""


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("demo")
def demo(
    auto_approve: Annotated[
        bool,
        typer.Option("--auto-approve", help="Approve every successfully ingested model."),
    ] = False,
) -> None:
    """Ingest the curated demo model list, sequentially, through the real pipeline.

    Each model is created and ingested exactly as an admin adding it through
    the UI would; a model whose slug already exists (any status) is skipped.
    Prints one line per model as it is processed, then a summary table. Exits
    1 only if every attempted (non-skipped) model failed.
    """
    results = asyncio.run(_demo(auto_approve))
    _print_summary(results)

    attempted = [result for result in results if result.outcome != "skipped"]
    if attempted and all(result.outcome == "failed" for result in attempted):
        raise typer.Exit(code=1)


async def _demo(auto_approve: bool) -> list[_SeedResult]:
    """Async half of `demo`: one broker connection, one session, every model.

    The broker connection is opened and closed around the whole run, because a
    one-off CLI process owns the Redis connection it opens (same contract as
    `app ingest run` and `app jobs ping`).
    """
    names = _load_names()
    await broker.startup()
    try:
        async with get_sessionmaker()() as session:
            return [await _seed_one(session, name, auto_approve) for name in names]
    finally:
        await broker.shutdown()


def _load_names() -> list[str]:
    """Read the curated model list; names only, everything else is derived."""
    payload = json.loads(SEED_MODELS_PATH.read_text())
    return [entry["name"] for entry in payload]


async def _seed_one(session: AsyncSession, name: str, auto_approve: bool) -> _SeedResult:
    """Seed one model: skip-if-exists, else ingest through the real pipeline."""
    slug = product_service.slugify(name)
    existing = await product_service.get_by_slug(session, slug)
    if existing is not None:
        typer.echo(f"{name}: skipped (exists: {existing.status.value})")
        return _SeedResult(name, "skipped", existing.status.value)

    motorbike = await product_service.create_backlog(session, name)
    operation = await product_service.start_ingestion(session, motorbike)
    typer.echo(f"{name}: ingesting (operation {operation.id})")

    operation = await _poll(session, operation)
    if operation.status is not OperationStatus.SUCCEEDED:
        detail = _failure_detail(operation)
        typer.echo(f"{name}: failed ({detail})")
        return _SeedResult(name, "failed", detail)

    typer.echo(f"{name}: seeded")
    if not auto_approve:
        return _SeedResult(name, "seeded")

    # The worker's own session moved the row to `in_review`; ours has neither
    # committed nor refreshed it since (`expire_on_commit=False`), so an
    # explicit refresh is required first — `transition` reading the stale
    # `ingesting` status here would raise `InvalidTransitionError` instead of
    # approving.
    await session.refresh(motorbike)
    try:
        await product_service.transition(session, motorbike, MotorbikeStatus.APPROVED)
    except product_service.IncompleteIdentityError as error:
        # D4 (step 6.12): approval now requires manufacturer/model/year, which
        # extraction only starts filling in step 6.15. Report-and-continue,
        # same as an ingestion failure, rather than crashing the whole run.
        typer.echo(f"{name}: failed ({error})")
        return _SeedResult(name, "failed", str(error))
    typer.echo(f"{name}: approved")
    return _SeedResult(name, "approved")


async def _poll(session: AsyncSession, operation: Operation) -> Operation:
    """Re-read `operation` until it is terminal or the timeout elapses.

    Uses `session.refresh` — an explicit, awaited reload, the same idiom
    `operation_service._save` already uses for its own server-defaulted
    column — rather than a fresh `operation_service.get` call: the operation
    is already identity-mapped in this session, and `get_sessionmaker()` sets
    `expire_on_commit=False`, so a plain re-select would hand back the same
    Python object without overwriting its already-loaded attributes (only an
    explicit expire or refresh does). Still non-terminal after the timeout
    elapses is treated as a failure by the caller, not retried further.
    """
    deadline = time.monotonic() + INGESTION_TIMEOUT_SECONDS
    while operation.status not in (OperationStatus.SUCCEEDED, OperationStatus.FAILED):
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        await session.refresh(operation)
    return operation


def _failure_detail(operation: Operation) -> str:
    """Describe why an operation did not succeed, for the report-and-continue line."""
    if operation.status is OperationStatus.FAILED:
        return operation.error or "ingestion failed"
    return f"timed out after {int(INGESTION_TIMEOUT_SECONDS)}s"


def _print_summary(results: list[_SeedResult]) -> None:
    """Print the final model -> outcome table, then a one-line totals count."""
    typer.echo("")
    typer.echo("Summary:")
    width = max((len(result.name) for result in results), default=0)
    for result in results:
        label = result.outcome
        if result.outcome in ("skipped", "failed"):
            label = f"{label} ({result.detail})"
        typer.echo(f"  {result.name:<{width}}  {label}")

    counts = Counter(result.outcome for result in results)
    typer.echo(
        f"{counts['seeded']} seeded, {counts['approved']} approved, "
        f"{counts['skipped']} skipped, {counts['failed']} failed."
    )


if __name__ == "__main__":  # pragma: no cover
    app()
