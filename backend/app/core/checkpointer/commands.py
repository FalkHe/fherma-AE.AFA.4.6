"""`app checkpoint ...` -- CLI commands for checkpointer setup.
Every command prints exactly one contract line to stdout on success and
nothing else; failures go to stderr with exit code 1, per this repo's existing
CLI modules (`core/llm/commands.py`, `core/prompts/commands.py`).

Callers use the module reference (`from app.core.checkpointer import service as
checkpointer_service`), never a name import."""

import asyncio

import typer

from app.core.checkpointer import service as checkpointer_service

checkpoint_app = typer.Typer()


def _fail(exc: Exception) -> typer.Exit:
    typer.echo(str(exc), err=True)
    return typer.Exit(code=1)


@checkpoint_app.command("setup")
def setup() -> None:
    try:
        asyncio.run(checkpointer_service.setup())
    except Exception as exc:
        raise _fail(exc) from exc
    typer.echo("checkpoints schema ready")
