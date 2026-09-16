"""WI3: `app srd ingest [--dry-run]` (`app/modules/srd/commands.py`).

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/srd/test_commands.py`'s style. `srd_service.
fetch_source` and `srd_service.chunk_source` are the only seams faked --
module attributes, never name imports, so the monkeypatch takes -- and the
network is never touched. No DB seam is faked because none should be
opened: neither branch of this command imports `app.core.db`.
"""

from pathlib import Path

from typer.testing import CliRunner

from app.cli import cli
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdSourceError
from app.modules.srd.schemas import RuleChunk

runner = CliRunner()


def _fake_chunks() -> list[RuleChunk]:
    return [
        RuleChunk(heading_path="Combat › Cover › Half Cover", ordinal=0, text="a", token_count=3),
        RuleChunk(heading_path="Combat › Another Rule", ordinal=0, text="b", token_count=5),
    ]


def test_dry_run_prints_stored_path_byte_count_chunk_and_token_totals_and_heading_sample(
    tmp_path, monkeypatch
):
    stored_path = tmp_path / "v1" / "SRD_CC_v5.1.md"
    stored_path.parent.mkdir(parents=True)
    stored_path.write_bytes(b"some source bytes")

    monkeypatch.setattr(srd_service, "fetch_source", lambda: stored_path)
    monkeypatch.setattr(srd_service, "chunk_source", lambda path: _fake_chunks())

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert str(stored_path) in result.stdout
    assert str(stored_path.stat().st_size) in result.stdout
    assert "2" in result.stdout  # chunk count
    assert "8" in result.stdout  # token total (3 + 5)
    assert "Combat › Cover › Half Cover" in result.stdout
    assert "Combat › Another Rule" in result.stdout


def test_dry_run_source_failure_prints_one_stderr_line_and_exits_1_with_no_traceback(
    monkeypatch,
):
    def _raise_fetch_source():
        raise SrdSourceError("could not reach SRD source https://example.invalid: boom")

    monkeypatch.setattr(srd_service, "fetch_source", _raise_fetch_source)

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert "could not reach SRD source" in result.stderr


def test_dry_run_opens_no_database_session(monkeypatch):
    import app.modules.srd.commands as commands_module

    def _forbidden():
        raise AssertionError("ingest --dry-run must not open a DB session")

    monkeypatch.setattr(commands_module, "get_sessionmaker", _forbidden)
    monkeypatch.setattr(srd_service, "fetch_source", lambda: Path("/dev/null"))
    monkeypatch.setattr(srd_service, "chunk_source", lambda path: [])

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])

    assert result.exit_code == 0, result.output


def test_bare_ingest_without_dry_run_exits_1_saying_embedding_not_landed_yet():
    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "embedding" in result.stderr.lower()
    assert "not" in result.stderr.lower()


def test_bare_ingest_opens_no_database_session(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        srd_service, "fetch_source", lambda: calls.append("fetch_source") or Path("/dev/null")
    )

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 1
    assert calls == []
