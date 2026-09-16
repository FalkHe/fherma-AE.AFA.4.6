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
        return CorpusStatus(rule_count=0, source_version=None, embedding_model=None, ingested_at=None)

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
