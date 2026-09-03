"""`app openapi` — export the OpenAPI schema without a running server.

The schema is produced by instantiating the FastAPI factory in-process, so it
stays available for frontend type generation even when PostgreSQL is down.
Nothing here may open a database connection.
"""

import json
from pathlib import Path
from typing import Annotated

import typer

from app.main import create_app

app = typer.Typer(
    help="Export the OpenAPI schema.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command()
def export(
    out: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Write the schema to this file instead of stdout.",
            dir_okay=False,
            writable=True,
        ),
    ] = None,
) -> None:
    """Print the OpenAPI schema as JSON, or write it to --out."""
    schema = json.dumps(create_app().openapi(), indent=2) + "\n"

    if out is None:
        typer.echo(schema, nl=False)
        return

    try:
        out.write_text(schema, encoding="utf-8")
    except OSError as error:
        typer.echo(f"Could not write {out}: {error.strerror}.", err=True)
        raise typer.Exit(code=1) from error

    typer.echo(f"Wrote OpenAPI schema to {out}.", err=True)


if __name__ == "__main__":  # pragma: no cover
    app()
