"""Root Typer application, exposed as the `app` console script."""

import typer

from app import __version__
from app.cli import (
    catalogue,
    chunks,
    embeddings,
    ingest,
    jobs,
    llm,
    openapi,
    operations,
    rag,
    retrieval,
    seed,
    snapshot,
    suggestions,
    tools,
    users,
)

app = typer.Typer(
    name="app",
    help="Motorcycle Buying Advisor administration CLI.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(catalogue.app, name="catalogue")
app.add_typer(chunks.app, name="chunks")
app.add_typer(embeddings.app, name="embeddings")
app.add_typer(ingest.app, name="ingest")
app.add_typer(jobs.app, name="jobs")
app.add_typer(llm.app, name="llm")
app.add_typer(openapi.app, name="openapi")
app.add_typer(operations.app, name="operations")
app.add_typer(rag.app, name="rag")
app.add_typer(retrieval.app, name="retrieval")
app.add_typer(seed.app, name="seed")
app.add_typer(snapshot.app, name="snapshot")
app.add_typer(suggestions.app, name="suggestions")
app.add_typer(tools.app, name="tools")
app.add_typer(users.app, name="users")


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command()
def version() -> None:
    """Print the application version."""
    typer.echo(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
