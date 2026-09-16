"""`app srd status` -- sprint 004-01 WI3, binding interface in
`docs/intents/004-srd-knowledge-base/sprints/01-empty-corpus-status/plan.md`
(I3).

Thin CLI over `srd/service.py` (WI2). The command opens its own DB session
via `app.core.db.get_sessionmaker` -- the same helper FastAPI's
`get_db_session` wraps -- because there is no request scope to hang a
`Depends(...)` off in a Typer command (no existing CLI command opens a
`DbSession` yet, so this follows the sessionmaker directly, per
`core/checkpointer/commands.py`'s precedent of running async work through
`asyncio.run(...)`).

Failure is one line to stderr plus `typer.Exit(code=1)`, per
`modules/content/commands.py` / `core/llm/commands.py`. `SrdVectorWidthError`
carries both widths in its own message (`service.check_vector_width`), so it
is echoed as-is. The empty-corpus case is not an exception -- `corpus_status`
returns `rule_count == 0` -- so the CLI spells out "0 rules" and the ingest
command itself (decided wording, sprint plan)."""

import asyncio

import typer

from app.core.db import get_sessionmaker
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdVectorWidthError
from app.modules.srd.schemas import CorpusStatus

srd_app = typer.Typer()

EMPTY_CORPUS_MESSAGE = "SRD corpus is empty: 0 rules ingested; run `app srd ingest` to load it."


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
