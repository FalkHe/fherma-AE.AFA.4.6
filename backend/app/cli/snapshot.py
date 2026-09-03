"""`app snapshot` — commit the curated catalogue to the repository, and restore it.

Two commands, both demo tooling (see `app.services.snapshot` for what the
archive contains and why it is not a `pg_dump`):

- `app snapshot save` reads the catalogue and writes the archive into
  `backend/resources/catalogue-snapshot/`, ready to commit. Read-only against
  the database.
- `app snapshot load` restores that archive into a fresh instance — rows,
  retained source payloads and images, embeddings included, so no OpenRouter
  key and no ingestion run are needed to get a working demo.

`load` refuses to touch a non-empty catalogue unless `--replace` is given.
`save` refuses to write over an existing archive unless `--force` is given, and
then clears the old one first, so a model deleted from the catalogue does not
survive as an orphaned file in the commit.

Follows the CLI async pattern of `app.cli.catalogue`: the Typer command body
stays synchronous and calls `asyncio.run(...)`; the async half owns the session.
"""

import asyncio
import shutil
from pathlib import Path
from typing import Annotated, NoReturn

import typer

from app.db.session import get_sessionmaker
from app.services import snapshot as snapshot_service

app = typer.Typer(
    help="Save the curated catalogue to the repository, or restore it (demo fixture).",
    no_args_is_help=True,
    add_completion=False,
)

DIRECTORY_HELP = "Snapshot directory; defaults to backend/resources/catalogue-snapshot."


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name."""


@app.command("save")
def save(
    directory: Annotated[
        Path | None,
        typer.Option("--dir", help=DIRECTORY_HELP),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Overwrite an existing snapshot in that directory."),
    ] = False,
) -> None:
    """Write the whole catalogue — rows, documents and images — into the archive.

    Nothing in the database is modified. Chat history, accounts and the
    operations log are deliberately not included.
    """
    target = directory or snapshot_service.DEFAULT_SNAPSHOT_DIR
    if _is_populated(target) and not force:
        _fail(f"{target} already holds a snapshot. Re-run with --force to overwrite it.")
    if _is_populated(target):
        _clear(target)

    try:
        report = asyncio.run(_save(target))
    except snapshot_service.SnapshotError as error:
        _fail(str(error))

    _print_report(report)
    typer.echo(f"Snapshot written to {target}.")


async def _save(target: Path) -> snapshot_service.SnapshotReport:
    """Async half of `save`: one session, read-only."""
    async with get_sessionmaker()() as session:
        return await snapshot_service.save(session, target)


@app.command("load")
def load(
    directory: Annotated[
        Path | None,
        typer.Option("--dir", help=DIRECTORY_HELP),
    ] = None,
    replace: Annotated[
        bool,
        typer.Option("--replace", help="Delete the existing catalogue rows first."),
    ] = False,
) -> None:
    """Restore the archived catalogue into this instance.

    Requires the schema to be migrated (`alembic upgrade head`, which the
    `app-web` entrypoint already runs). Refuses to run against a non-empty
    catalogue unless `--replace` is given; `users`, `chats` and `operations`
    are never touched either way.
    """
    source = directory or snapshot_service.DEFAULT_SNAPSHOT_DIR

    try:
        report = asyncio.run(_load(source, replace=replace))
    except snapshot_service.SnapshotError as error:
        _fail(str(error))

    _print_report(report)
    typer.echo(f"Snapshot restored from {source}.")


async def _load(source: Path, *, replace: bool) -> snapshot_service.SnapshotReport:
    """Async half of `load`: one session, one transaction for the rows."""
    async with get_sessionmaker()() as session:
        return await snapshot_service.load(session, source, replace=replace)


def _is_populated(directory: Path) -> bool:
    """True when `directory` already contains a snapshot manifest."""
    return (directory / snapshot_service.MANIFEST_NAME).is_file()


def _clear(directory: Path) -> None:
    """Remove a previous snapshot's contents, leaving the directory itself.

    Only the three archive sub-trees and the manifest are removed, so an
    accidental `--dir` pointing at a directory with other contents cannot turn
    into a recursive delete of unrelated files.
    """
    (directory / snapshot_service.MANIFEST_NAME).unlink(missing_ok=True)
    for name in (
        snapshot_service.TABLES_DIRECTORY,
        snapshot_service.DATA_DIRECTORY,
        snapshot_service.MEDIA_DIRECTORY,
    ):
        shutil.rmtree(directory / name, ignore_errors=True)


def _print_report(report: snapshot_service.SnapshotReport) -> None:
    """Print the per-table counts, then the payload totals."""
    width = max((len(name) for name in report.tables), default=0)
    for name, rows in report.tables.items():
        typer.echo(f"  {name:<{width}}  {rows} row(s)")
    typer.echo(
        f"{report.total_rows} row(s), {report.data_files} source payload(s), "
        f"{report.media_files} image file(s)."
    )
    if report.missing_files:
        typer.echo(f"{len(report.missing_files)} referenced file(s) not on disk:", err=True)
        for relative_path in sorted(report.missing_files):
            typer.echo(f"  missing: {relative_path}", err=True)


def _fail(message: str) -> NoReturn:
    """Report why nothing was written and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
