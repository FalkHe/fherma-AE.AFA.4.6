"""WI3: `app srd status` (`app/modules/srd/commands.py`, registered in
`app/cli.py` as `cli.add_typer(srd_app, name="srd")`).

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/core/checkpointer/test_commands.py`'s style.
The only seam faked is `srd_service.corpus_status` (module attribute, never
a name import, so the monkeypatch takes). `_fetch_status` also opens a
session via `app.core.db.get_sessionmaker()`, but that only builds a lazy
`AsyncEngine` -- SQLAlchemy never opens a socket until a statement actually
runs -- so leaving it real here stays engine-free exactly like
`tests/srd/test_acceptance_empty_corpus_status.py`'s AC3 case: the faked
`corpus_status` never issues a query."""

from datetime import UTC, datetime

from typer.testing import CliRunner

from app.cli import cli
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdVectorWidthError
from app.modules.srd.schemas import CorpusStatus

runner = CliRunner()


def test_status_on_empty_corpus_exits_1_with_stderr_naming_zero_rules_and_the_ingest_command(
    monkeypatch,
):
    async def fake_corpus_status(db):
        return CorpusStatus(
            rule_count=0, source_version=None, embedding_model=None, ingested_at=None
        )

    monkeypatch.setattr(srd_service, "corpus_status", fake_corpus_status)

    result = runner.invoke(cli, ["srd", "status"])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "0" in result.stderr
    assert "rule" in result.stderr.lower()
    assert "app srd ingest" in result.stderr


def test_status_on_populated_corpus_exits_0_with_count_model_and_ingest_time_on_stdout(
    monkeypatch,
):
    ingested_at = datetime(2026, 1, 1, tzinfo=UTC)

    async def fake_corpus_status(db):
        return CorpusStatus(
            rule_count=42,
            source_version="v1",
            embedding_model="test/embedding-model",
            ingested_at=ingested_at,
        )

    monkeypatch.setattr(srd_service, "corpus_status", fake_corpus_status)

    result = runner.invoke(cli, ["srd", "status"])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert "42" in result.stdout
    assert "test/embedding-model" in result.stdout
    assert str(ingested_at) in result.stdout


def test_status_on_vector_width_mismatch_exits_1_with_stderr_naming_both_widths(monkeypatch):
    async def failing_corpus_status(db):
        raise SrdVectorWidthError(
            "configured embedding width 4 does not match the srd_rules column width 1536"
        )

    monkeypatch.setattr(srd_service, "corpus_status", failing_corpus_status)

    result = runner.invoke(cli, ["srd", "status"])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "4" in result.stderr
    assert "1536" in result.stderr


def test_ingest_without_dry_run_exits_1_naming_sprint_03(monkeypatch):
    result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "sprint 03" in result.stderr


def test_ingest_dry_run_prints_path_byte_count_chunk_count_tokens_and_sample_headings(
    monkeypatch, tmp_path
):
    from app.modules.srd.schemas import RuleChunk

    fixture_path = tmp_path / "SRD_CC_v5.1.md"
    fixture_path.write_bytes(b"some markdown source")

    monkeypatch.setattr(srd_service, "fetch_source", lambda: fixture_path)
    monkeypatch.setattr(
        srd_service,
        "chunk_source",
        lambda path: [
            RuleChunk(
                heading_path="Combat › Cover › Half Cover", ordinal=0, text="x", token_count=5
            ),
            RuleChunk(
                heading_path="Combat › Cover › Half Cover", ordinal=1, text="y", token_count=3
            ),
            RuleChunk(heading_path="Combat › Actions", ordinal=0, text="z", token_count=7),
        ],
    )

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert str(fixture_path) in result.stdout
    assert str(len(fixture_path.read_bytes())) in result.stdout
    assert "3" in result.stdout  # chunk count
    assert "15" in result.stdout  # total tokens
    assert "Combat › Cover › Half Cover" in result.stdout
    assert "Combat › Actions" in result.stdout


def test_ingest_dry_run_on_srd_source_error_exits_1_with_its_message(monkeypatch):
    from app.modules.srd.errors import SrdSourceError

    def failing_fetch():
        raise SrdSourceError("the source could not be reached")

    monkeypatch.setattr(srd_service, "fetch_source", failing_fetch)

    result = runner.invoke(cli, ["srd", "ingest", "--dry-run"])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "the source could not be reached" in result.stderr
