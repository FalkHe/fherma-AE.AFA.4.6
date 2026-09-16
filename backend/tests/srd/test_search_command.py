"""`app srd search QUERY [--limit N]` (`app/modules/srd/commands.py`) --
sprint 004-05 WI2.

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/srd/test_ingest_command.py`'s style: the only
seam faked is `srd_service.search_rules` (a module attribute, never a name
import, so the monkeypatch takes) -- `get_sessionmaker` is left real, since
it only builds a lazy `AsyncEngine` that never opens a socket until a
statement runs, and the faked `search_rules` never issues one. The network
is never touched and no real embedding call is ever made. Engine-free.
"""

from typer.testing import CliRunner

from app.cli import cli
from app.core.llm.errors import LlmRateLimitError
from app.modules.srd import commands as commands_module
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdCorpusEmptyError, SrdVectorWidthError
from app.modules.srd.schemas import RuleMatch

runner = CliRunner()


def _matches() -> list[RuleMatch]:
    return [
        RuleMatch(
            heading_path="Combat › Cover › Half Cover",
            ordinal=0,
            text="You have half cover if an obstacle blocks at least half of your body.",
            score=0.914,
        ),
        RuleMatch(
            heading_path="Combat › Cover › Three-Quarters Cover",
            ordinal=1,
            text="You have three-quarters cover if three-quarters of your body is blocked.",
            score=0.512,
        ),
    ]


def test_results_print_citation_score_and_passage_best_first(monkeypatch):
    captured: dict = {}

    async def fake_search_rules(db, query, *, limit=srd_service.DEFAULT_LIMIT):
        captured["query"] = query
        captured["limit"] = limit
        return _matches()

    monkeypatch.setattr(srd_service, "search_rules", fake_search_rules)

    result = runner.invoke(cli, ["srd", "search", "how does half cover work"])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert captured["query"] == "how does half cover work"

    first_match, second_match = _matches()
    first_index = result.stdout.index(first_match.heading_path)
    second_index = result.stdout.index(second_match.heading_path)
    assert first_index < second_index, result.stdout

    for match in _matches():
        assert match.heading_path in result.stdout
        assert str(match.ordinal) in result.stdout
        assert f"{match.score:.3f}" in result.stdout
        assert match.text in result.stdout


def test_limit_option_is_passed_through_to_search_rules(monkeypatch):
    captured: dict = {}

    async def fake_search_rules(db, query, *, limit=srd_service.DEFAULT_LIMIT):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(srd_service, "search_rules", fake_search_rules)

    result = runner.invoke(cli, ["srd", "search", "half cover", "--limit", "3"])

    assert result.exit_code == 0, result.output
    assert captured["limit"] == 3


def test_omitted_limit_falls_back_to_default_limit(monkeypatch):
    captured: dict = {}

    async def fake_search_rules(db, query, *, limit=srd_service.DEFAULT_LIMIT):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(srd_service, "search_rules", fake_search_rules)

    result = runner.invoke(cli, ["srd", "search", "half cover"])

    assert result.exit_code == 0, result.output
    assert captured["limit"] == srd_service.DEFAULT_LIMIT


def test_empty_corpus_exits_nonzero_with_the_empty_corpus_message(monkeypatch):
    async def fake_search_rules(db, query, *, limit=srd_service.DEFAULT_LIMIT):
        raise SrdCorpusEmptyError("the SRD corpus holds no rules; run `app srd ingest` first")

    monkeypatch.setattr(srd_service, "search_rules", fake_search_rules)

    result = runner.invoke(cli, ["srd", "search", "half cover"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert result.stderr.strip() == commands_module.EMPTY_CORPUS_MESSAGE


def test_other_srd_error_prints_one_stderr_line_and_exits_1_with_no_traceback(monkeypatch):
    async def fake_search_rules(db, query, *, limit=srd_service.DEFAULT_LIMIT):
        raise SrdVectorWidthError(
            "configured embedding width 4 does not match the srd_rules column width 1536"
        )

    monkeypatch.setattr(srd_service, "search_rules", fake_search_rules)

    result = runner.invoke(cli, ["srd", "search", "half cover"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert "4" in result.stderr
    assert "1536" in result.stderr


def test_gateway_failure_prints_one_stderr_line_naming_its_code_and_exits_1(monkeypatch):
    async def fake_search_rules(db, query, *, limit=srd_service.DEFAULT_LIMIT):
        raise LlmRateLimitError("simulated rate limit mid-search")

    monkeypatch.setattr(srd_service, "search_rules", fake_search_rules)

    result = runner.invoke(cli, ["srd", "search", "half cover"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Traceback" not in result.output
    stderr_lines = [line for line in result.stderr.splitlines() if line.strip()]
    assert len(stderr_lines) == 1, result.stderr
    assert "LLM_RATE_LIMIT" in result.stderr
