"""`app checkpoint ...` -- sprint 07 WI3, binding interface in
`docs/intents/001-llm-access-scaffolding/sprints/07-agent-checkpoints/research.md`
(the CLI line of "Interfaces").

Thin CLI over `core/checkpointer/service.py` (schema/connection plumbing,
WI1) and `core/checkpointer/demo_graph.py` (the throwaway interrupt/resume
fixture that module's own docstring disclaims). Every command prints
exactly one contract line to stdout on success and nothing else; failures
go to stderr with exit code 1, per this repo's existing CLI modules
(`core/llm/commands.py`, `core/prompts/commands.py`).

Callers use the module reference for both (`from app.core.checkpointer
import demo_graph`, `... import service as checkpointer_service`), never a
name import - consistent with `service.py`'s own stated convention, and
what lets the tests monkeypatch either seam."""

import asyncio
import json

import typer

from app.core.checkpointer import demo_graph
from app.core.checkpointer import service as checkpointer_service

checkpoint_app = typer.Typer()
demo_app = typer.Typer()
checkpoint_app.add_typer(demo_app, name="demo")


def _fail(exc: Exception) -> typer.Exit:
    # One generic line for any failure (no domain error type exists for
    # this module - see service.py/demo_graph.py): the CLI's contract is
    # only "stdout carries the one success line, stderr carries failure,
    # exit 1", not a specific message shape.
    typer.echo(str(exc), err=True)
    return typer.Exit(code=1)


@checkpoint_app.command("setup")
def setup() -> None:
    try:
        asyncio.run(checkpointer_service.setup())
    except Exception as exc:
        raise _fail(exc) from exc
    typer.echo("checkpoints schema ready")


@demo_app.command("start")
def start(thread: str = typer.Option(..., "--thread")) -> None:
    async def _run() -> object:
        async with checkpointer_service.checkpointer() as saver:
            return await demo_graph.start(saver, thread)

    try:
        value = asyncio.run(_run())
    except Exception as exc:
        raise _fail(exc) from exc
    typer.echo(f"interrupted: {json.dumps(value)}")


@demo_app.command("resume")
def resume(
    thread: str = typer.Option(..., "--thread"),
    value: str = typer.Option(..., "--value"),
) -> None:
    async def _run() -> str:
        async with checkpointer_service.checkpointer() as saver:
            return await demo_graph.resume(saver, thread, value)

    try:
        answer = asyncio.run(_run())
    except Exception as exc:
        raise _fail(exc) from exc
    typer.echo(f"answer: {answer}")
