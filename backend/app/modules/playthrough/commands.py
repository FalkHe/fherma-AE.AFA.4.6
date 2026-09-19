"""`app playthrough cost` -- sprint 005/05b WI1, binding interface in
`docs/intents/005-game-state-services/sprints/05b-cost-and-live-signal/plan.md`
(I2).

Thin CLI over `playthrough/service.py`'s `run_cost` (WI1). The command opens
its own DB session via `app.core.db.get_sessionmaker` -- the same helper
FastAPI's `get_db_session` wraps -- exactly the way `srd/commands.py`'s
`status` command does it, because there is no request scope to hang a
`Depends(...)` off in a Typer command.

This is cost's *only* address (← D14): no HTTP route ever exposes it.
Failure is `f"{exc.code}: {exc}"` to stderr plus `typer.Exit(code=1)`, per
`modules/srd/commands.py` -- a foreign or unknown run prints `NOT_FOUND`.
"""

import asyncio

import typer

from app.core.db import get_sessionmaker
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import PlaythroughError
from app.modules.playthrough.schemas import RunCost

playthrough_app = typer.Typer()


async def _fetch_cost(*, run_id: str, user_id: str) -> RunCost:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        return await playthrough_service.run_cost(db, user_id=user_id, run_id=run_id)


@playthrough_app.command("cost")
def cost(
    run_id: str = typer.Argument(..., help="The campaign run id."),
    user_id: str = typer.Option(..., "--user", help="The caller's user id."),
) -> None:
    try:
        result = asyncio.run(_fetch_cost(run_id=run_id, user_id=user_id))
    except PlaythroughError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"run: {run_id}")
    typer.echo(f"total: {result.total:.6f}")
    for turn in result.turns:
        label = turn.turn_id if turn.turn_id is not None else "-"
        typer.echo(f"turn {label}: {turn.total:.6f}")
