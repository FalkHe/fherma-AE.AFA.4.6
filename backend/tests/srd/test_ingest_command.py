"""`app srd ingest [--dry-run]` (`app/modules/srd/commands.py`) -- sprint
004-02 WI3 landed `--dry-run`; sprint 004-03 WI2 adds the real, DB-backed
bare path.

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/srd/test_commands.py`'s style. `--dry-run`
fakes only `srd_service.fetch_source` / `srd_service.chunk_source` --
module attributes, never name imports, so the monkeypatch takes -- and
opens no DB session at all. The bare path fakes `srd_service.ingest`
itself (its own behaviour is `tests/srd/test_ingest_service.py`'s job);
`get_sessionmaker` is left real, exactly like `test_commands.py`'s
`status` tests -- it only builds a lazy `AsyncEngine` that never opens a
socket until a statement runs, and the faked `ingest` never issues one.
The network is never touched either way, and no real embedding call is
ever made.
"""

from pathlib import Path

from typer.testing import CliRunner

from app.cli import cli
from app.core.llm.errors import LlmRateLimitError
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdSourceError, SrdVectorWidthError
from app.modules.srd.schemas import IngestReport, RuleChunk

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


def test_bare_ingest_prints_one_progress_line_per_batch_then_the_full_report(monkeypatch):
    async def fake_ingest(db, *, version=srd_service.SOURCE_VERSION, on_batch=None):
        on_batch(2, 5)
        on_batch(5, 5)
        return IngestReport(
            source_version="v1",
            source_bytes=1234,
            chunk_count=5,
            token_count=999,
            cost_usd=0.05,
            cost_complete=True,
        )

    monkeypatch.setattr(srd_service, "ingest", fake_ingest)

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    progress_lines = [line for line in result.stdout.splitlines() if "2/5" in line or "5/5" in line]
    assert len(progress_lines) == 2, result.stdout
    assert "v1" in result.stdout
    assert "1234" in result.stdout
    assert "5" in result.stdout  # chunk count
    assert "999" in result.stdout
    assert "0.05" in result.stdout


def test_bare_ingest_reports_a_complete_cost_as_the_total(monkeypatch):
    async def fake_ingest(db, *, version=srd_service.SOURCE_VERSION, on_batch=None):
        return IngestReport(
            source_version="v1",
            source_bytes=1,
            chunk_count=1,
            token_count=1,
            cost_usd=1.5,
            cost_complete=True,
        )

    monkeypatch.setattr(srd_service, "ingest", fake_ingest)

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 0, result.output
    assert "1.500000" in result.stdout
    assert "total" in result.stdout.lower()
    assert "at least" not in result.stdout.lower()


def test_bare_ingest_reports_an_incomplete_cost_as_a_labelled_lower_bound(monkeypatch):
    async def fake_ingest(db, *, version=srd_service.SOURCE_VERSION, on_batch=None):
        return IngestReport(
            source_version="v1",
            source_bytes=1,
            chunk_count=1,
            token_count=1,
            cost_usd=1.5,
            cost_complete=False,
        )

    monkeypatch.setattr(srd_service, "ingest", fake_ingest)

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 0, result.output
    assert "1.500000" in result.stdout
    assert "at least" in result.stdout.lower()


def test_bare_ingest_reports_no_priced_batch_as_unavailable(monkeypatch):
    async def fake_ingest(db, *, version=srd_service.SOURCE_VERSION, on_batch=None):
        return IngestReport(
            source_version="v1",
            source_bytes=1,
            chunk_count=1,
            token_count=1,
            cost_usd=None,
            cost_complete=True,
        )

    monkeypatch.setattr(srd_service, "ingest", fake_ingest)

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 0, result.output
    assert "unavailable" in result.stdout.lower()


def test_bare_ingest_gateway_failure_prints_one_stderr_line_naming_its_code_and_exits_1(
    monkeypatch,
):
    async def failing_ingest(db, *, version=srd_service.SOURCE_VERSION, on_batch=None):
        on_batch(1, 5)  # a batch may already have succeeded before the failure
        raise LlmRateLimitError("simulated rate limit mid-ingest")

    monkeypatch.setattr(srd_service, "ingest", failing_ingest)

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert "LLM_RATE_LIMIT" in result.stderr


def test_bare_ingest_source_failure_prints_one_stderr_line_and_exits_1_with_no_traceback(
    monkeypatch,
):
    async def failing_ingest(db, *, version=srd_service.SOURCE_VERSION, on_batch=None):
        raise SrdSourceError("could not reach SRD source https://example.invalid: boom")

    monkeypatch.setattr(srd_service, "ingest", failing_ingest)

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert "could not reach SRD source" in result.stderr


def test_bare_ingest_vector_width_failure_prints_one_stderr_line_and_exits_1(monkeypatch):
    async def failing_ingest(db, *, version=srd_service.SOURCE_VERSION, on_batch=None):
        raise SrdVectorWidthError(
            "configured embedding width 4 does not match the srd_rules column width 1536"
        )

    monkeypatch.setattr(srd_service, "ingest", failing_ingest)

    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert "4" in result.stderr
    assert "1536" in result.stderr
