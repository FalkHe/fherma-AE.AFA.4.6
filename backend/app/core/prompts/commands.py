"""`app prompt show` -- sprint 06 WI2, binding interface in
`docs/intents/001-llm-access-scaffolding/sprints/06-prompt-assets/research.md`.

Thin CLI over `core/prompts/service.py`'s resolver (WI1): this module never
touches the filesystem or the id grammar itself, it only shapes the
resolver's result and errors for the terminal.

Output contract (AC1, AC3, AC4): stdout carries the resolved prompt's text
and nothing else -- so `app prompt show ... | diff - <file>` passes -- while
the `resolved: <prompt_id> <version>` line (AC3) goes to stderr. Failures
also go to stderr, with `PromptNotFoundError` and `PromptIdInvalidError`
(AC4) mapped to distinct exit codes (3 and 2) and each carrying its own
error code in the text, so a test can assert the code and the exit status
independently.
"""

import typer

from app.core.prompts import service as prompt_service
from app.core.prompts.errors import PromptError, PromptIdInvalidError, PromptNotFoundError

prompt_app = typer.Typer()


@prompt_app.command("show")
def show(
    prompt_id: str = typer.Argument(...),
    version: str | None = typer.Option(None, "--version"),
) -> None:
    try:
        resolved = prompt_service.load_prompt(prompt_id, version=version)
    except PromptNotFoundError as exc:
        typer.echo(f"not found: {exc.relative_path} [{exc.code}]", err=True)
        raise typer.Exit(code=3) from exc
    except PromptIdInvalidError as exc:
        typer.echo(f"invalid prompt id: {exc.value} ({exc.reason}) [{exc.code}]", err=True)
        raise typer.Exit(code=2) from exc
    except PromptError as exc:
        # Catch-all for any future `PromptError` subclass that is neither
        # of the two above; the resolver's own contract names only those
        # two, so this path is defensive, not expected to run.
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc

    # Verbatim, no added or stripped newline (AC1): the file's own bytes
    # are the resolver's `.text`, unmodified.
    typer.echo(resolved.text, nl=False)
    typer.echo(f"resolved: {resolved.prompt_id} {resolved.version}", err=True)
