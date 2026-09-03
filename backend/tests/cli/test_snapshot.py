"""Tests for `app snapshot save` / `app snapshot load`.

The engine itself is covered by `tests/services/test_snapshot.py`; what is
proven here is the CLI contract, which is entirely about not destroying
anything by accident: neither an existing archive in the working tree nor an
existing catalogue in the database. `snapshot_service.save` / `.load` are
replaced, so no database is touched.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli.main import app as cli
from app.services import snapshot as snapshot_service

runner = CliRunner()


@pytest.fixture
def default_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the committed default archive location to a scratch directory.

    Without this the outcome of a `save` with no `--dir` would depend on whether
    the developer's working tree currently holds a snapshot.
    """
    directory = tmp_path / "default-snapshot"
    monkeypatch.setattr(snapshot_service, "DEFAULT_SNAPSHOT_DIR", directory)
    return directory


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """A directory holding a snapshot manifest, plus the three sub-trees."""
    directory = tmp_path / "catalogue-snapshot"
    for name in (
        snapshot_service.TABLES_DIRECTORY,
        snapshot_service.DATA_DIRECTORY,
        snapshot_service.MEDIA_DIRECTORY,
    ):
        (directory / name).mkdir(parents=True)
    (directory / snapshot_service.MANIFEST_NAME).write_text(json.dumps({"snapshot_version": 1}))
    (directory / snapshot_service.TABLES_DIRECTORY / "stale.jsonl.gz").write_bytes(b"old")
    return directory


@pytest.fixture
def recorded_saves(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record the directory `save` was asked to write, without writing it."""
    targets: list[Path] = []

    async def record(session: object, target: Path) -> snapshot_service.SnapshotReport:
        targets.append(target)
        return snapshot_service.SnapshotReport(tables={"motorbikes": 3}, data_files=1)

    monkeypatch.setattr(snapshot_service, "save", record)
    monkeypatch.setattr("app.cli.snapshot.get_sessionmaker", lambda: _NullSessionFactory())
    return targets


@pytest.fixture
def recorded_loads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, bool]]:
    """Record the (directory, replace) `load` was called with."""
    calls: list[tuple[Path, bool]] = []

    async def record(
        session: object, source: Path, *, replace: bool
    ) -> snapshot_service.SnapshotReport:
        calls.append((source, replace))
        return snapshot_service.SnapshotReport(tables={"motorbikes": 3}, media_files=4)

    monkeypatch.setattr(snapshot_service, "load", record)
    monkeypatch.setattr("app.cli.snapshot.get_sessionmaker", lambda: _NullSessionFactory())
    return calls


class _NullSessionFactory:
    """`async with get_sessionmaker()() as session:` without a database."""

    def __call__(self) -> "_NullSessionFactory":
        return self

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def test_save_writes_to_the_committed_default_directory(
    default_directory: Path, recorded_saves: list[Path]
) -> None:
    result = runner.invoke(cli, ["snapshot", "save"])

    assert result.exit_code == 0
    assert recorded_saves == [default_directory]
    assert "3 row(s)" in result.stdout


def test_save_refuses_to_overwrite_an_existing_archive(
    archive: Path, recorded_saves: list[Path]
) -> None:
    """The archive is a committed artefact; clobbering it must be deliberate."""
    result = runner.invoke(cli, ["snapshot", "save", "--dir", str(archive)])

    assert result.exit_code == 1
    assert "--force" in result.output
    assert recorded_saves == []


def test_force_clears_the_previous_archive_first(archive: Path, recorded_saves: list[Path]) -> None:
    """A model deleted from the catalogue must not survive as an orphaned file."""
    result = runner.invoke(cli, ["snapshot", "save", "--dir", str(archive), "--force"])

    assert result.exit_code == 0
    assert recorded_saves == [archive]
    assert not (archive / snapshot_service.TABLES_DIRECTORY / "stale.jsonl.gz").exists()
    assert not (archive / snapshot_service.MANIFEST_NAME).exists()


def test_force_leaves_unrelated_files_in_the_directory_alone(
    archive: Path, recorded_saves: list[Path]
) -> None:
    """`--dir` pointed somewhere unexpected must not become a recursive delete."""
    bystander = archive / "notes.md"
    bystander.write_text("mine")

    runner.invoke(cli, ["snapshot", "save", "--dir", str(archive), "--force"])

    assert bystander.read_text() == "mine"


def test_load_defaults_to_the_committed_directory_and_does_not_replace(
    default_directory: Path, recorded_loads: list[tuple[Path, bool]]
) -> None:
    result = runner.invoke(cli, ["snapshot", "load"])

    assert result.exit_code == 0
    assert recorded_loads == [(default_directory, False)]
    assert "4 image file(s)" in result.stdout


def test_load_passes_replace_through(recorded_loads: list[tuple[Path, bool]]) -> None:
    result = runner.invoke(cli, ["snapshot", "load", "--dir", "/tmp/snap", "--replace"])

    assert result.exit_code == 0
    assert recorded_loads == [(Path("/tmp/snap"), True)]


def test_a_snapshot_error_is_reported_and_exits_non_zero(
    default_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refused load (non-empty catalogue, bad manifest) must not look like success."""

    async def refuse(session: object, source: Path, *, replace: bool) -> None:
        raise snapshot_service.SnapshotError("The catalogue is not empty (motorbikes=208).")

    monkeypatch.setattr(snapshot_service, "load", refuse)
    monkeypatch.setattr("app.cli.snapshot.get_sessionmaker", lambda: _NullSessionFactory())

    result = runner.invoke(cli, ["snapshot", "load"])

    assert result.exit_code == 1
    assert "The catalogue is not empty (motorbikes=208)." in result.output


def test_missing_payload_files_are_listed(
    default_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A snapshot with a gap is still written, but the gap is never silent."""

    async def with_gap(session: object, target: Path) -> snapshot_service.SnapshotReport:
        return snapshot_service.SnapshotReport(
            tables={"motorbikes": 1}, missing_files=["sources/a/b.html"]
        )

    monkeypatch.setattr(snapshot_service, "save", with_gap)
    monkeypatch.setattr("app.cli.snapshot.get_sessionmaker", lambda: _NullSessionFactory())

    result = runner.invoke(cli, ["snapshot", "save"])

    assert result.exit_code == 0
    assert "missing: sources/a/b.html" in result.output
