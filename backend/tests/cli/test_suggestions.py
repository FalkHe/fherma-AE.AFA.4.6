"""Tests for `app suggestions import`.

Two halves, tested separately. The parser is pure text work, so it is exercised
directly against the shapes the real list contains (multiple year ranges,
"present", type codes, footnote references, junk lines). The command is
exercised through the Typer runner against the in-memory `FakeAsyncSession`
other CLI tests use (`tests/services/conftest.py`), so the real create /
skip / enrich logic runs end to end without a database or an event loop of our
own. No broker is stubbed, because this command enqueues nothing — proving that
is one of the tests.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from app.cli import suggestions as suggestions_cli
from app.cli.main import app as cli
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from tests.services.conftest import FakeAsyncSession

runner = CliRunner()

LIST_TEXT = """\
BMW R 1200 GS (2004–2018) [K25/K50] ([Wikipedia][1])
Kawasaki Ninja ZX-6R (1995–2016, 2019–2020, 2024–present) [ZX600/ZX636]
Suzuki SV 650 (1999–2012, 2016–present)
Triumph Rocket III (2004–2017) ([Wikipedia][2])

[1]: https://de.wikipedia.org/wiki/BMW_R_1200_GS_K25 "BMW R 1200 GS K25"
[2]: https://de.wikipedia.org/wiki/Liste_der_Triumph-Motorr%C3%A4der "Triumph"
"""


class _SessionContextManager:
    """Adapts a `FakeAsyncSession` to the `async with sessionmaker() as s:` shape."""

    def __init__(self, session: FakeAsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeAsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture(autouse=True)
def _patch_sessionmaker(monkeypatch: pytest.MonkeyPatch, fake_session: FakeAsyncSession) -> None:
    monkeypatch.setattr(
        "app.cli.suggestions.get_sessionmaker",
        lambda: lambda: _SessionContextManager(fake_session),
    )


@pytest.fixture
def list_path(tmp_path: Path) -> Path:
    path = tmp_path / "bike-list.txt"
    path.write_text(LIST_TEXT, encoding="utf-8")
    return path


def _parse(text: str) -> tuple[dict[str, dict], list[str]]:
    models, warnings = suggestions_cli.parse_list(text, source="bike-list.txt")
    return {model.name: model.suggestion for model in models}, warnings


def test_parses_a_closed_range_with_type_codes_and_a_footnote_link() -> None:
    parsed, warnings = _parse(LIST_TEXT)

    assert warnings == []
    assert parsed["BMW R 1200 GS"] == {
        "source": "bike-list.txt",
        "raw": "BMW R 1200 GS (2004–2018) [K25/K50] ([Wikipedia][1])",
        "manufacturer": "BMW",
        "model": "R 1200 GS",
        "year_from": 2004,
        "year_to": 2018,
        "in_production": False,
        "year_ranges": [{"from": 2004, "to": 2018}],
        "type_codes": ["K25", "K50"],
        "links": ["https://de.wikipedia.org/wiki/BMW_R_1200_GS_K25"],
    }


def test_parses_several_ranges_and_leaves_an_open_end_open() -> None:
    parsed, _ = _parse(LIST_TEXT)
    zx6r = parsed["Kawasaki Ninja ZX-6R"]

    assert zx6r["year_ranges"] == [
        {"from": 1995, "to": 2016},
        {"from": 2019, "to": 2020},
        {"from": 2024, "to": None},
    ]
    # The span starts at the earliest year and has no end while it is built.
    assert (zx6r["year_from"], zx6r["year_to"], zx6r["in_production"]) == (1995, None, True)


def test_an_entry_without_codes_or_links_still_parses() -> None:
    parsed, _ = _parse(LIST_TEXT)

    assert parsed["Suzuki SV 650"]["type_codes"] == []
    assert parsed["Suzuki SV 650"]["links"] == []


def test_a_reference_without_a_definition_costs_only_the_link() -> None:
    parsed, warnings = _parse("Honda CB 500 F (2013–2018) ([Wikipedia][9])\n")

    assert warnings == []
    assert parsed["Honda CB 500 F"]["links"] == []
    assert parsed["Honda CB 500 F"]["year_from"] == 2013


def test_a_single_year_becomes_a_range_of_one() -> None:
    parsed, _ = _parse("Ducati Monster 695 (2006)\n")
    monster = parsed["Ducati Monster 695"]

    assert monster["year_ranges"] == [{"from": 2006, "to": 2006}]
    assert (monster["year_from"], monster["year_to"]) == (2006, 2006)


def test_a_line_with_no_usable_name_is_reported_not_imported() -> None:
    parsed, warnings = _parse("??? (2006)\n")

    assert parsed == {}
    assert len(warnings) == 1


def test_a_name_the_list_repeats_is_imported_once() -> None:
    parsed, warnings = _parse("Suzuki SV 650 (1999–2012)\nSuzuki SV 650 (2016–present)\n")

    assert list(parsed) == ["Suzuki SV 650"]
    assert parsed["Suzuki SV 650"]["year_ranges"] == [{"from": 1999, "to": 2012}]
    assert any("Duplicate" in warning for warning in warnings)


def test_import_creates_one_backlog_entry_per_line_and_ingests_nothing(
    fake_session: FakeAsyncSession, list_path: Path
) -> None:
    result = runner.invoke(cli, ["suggestions", "import", str(list_path)])

    assert result.exit_code == 0, result.output
    motorbikes = fake_session.rows(Motorbike)
    assert [motorbike.query_name for motorbike in motorbikes] == [
        "BMW R 1200 GS",
        "Kawasaki Ninja ZX-6R",
        "Suzuki SV 650",
        "Triumph Rocket III",
    ]
    # Suggestions are proposals: backlog, and no operation was ever created.
    assert {motorbike.status for motorbike in motorbikes} == {MotorbikeStatus.BACKLOG}
    assert "4 added" in result.output


def test_import_stores_the_claims_without_touching_the_typed_columns(
    fake_session: FakeAsyncSession, list_path: Path
) -> None:
    runner.invoke(cli, ["suggestions", "import", str(list_path)])

    gs = next(row for row in fake_session.rows(Motorbike) if row.query_name == "BMW R 1200 GS")
    assert gs.suggestion["year_from"] == 2004
    assert gs.suggestion["type_codes"] == ["K25", "K50"]
    # Only research fills these in — a claim is not a fact.
    assert (gs.manufacturer_id, gs.model_name, gs.year_from, gs.year_to) == (None, None, None, None)


def test_import_announces_every_row_it_wrote(
    fake_session: FakeAsyncSession, list_path: Path
) -> None:
    runner.invoke(cli, ["suggestions", "import", str(list_path)])

    channels = [channel for channel, _ in fake_session.notifications]
    assert len(channels) == 4


def test_import_leaves_an_existing_entry_alone(
    fake_session: FakeAsyncSession, list_path: Path
) -> None:
    existing = Motorbike(
        query_name="Suzuki SV 650",
        slug="suzuki-sv-650",
        status=MotorbikeStatus.APPROVED,
        suggestion={"source": "earlier"},
    )
    fake_session.add(existing)

    result = runner.invoke(cli, ["suggestions", "import", str(list_path)])

    assert existing.status is MotorbikeStatus.APPROVED
    assert existing.suggestion == {"source": "earlier"}
    assert "3 added, 0 enriched, 1 skipped" in result.output


def test_import_attaches_the_suggestion_to_an_entry_that_has_none(
    fake_session: FakeAsyncSession, list_path: Path
) -> None:
    existing = Motorbike(
        query_name="Suzuki SV 650", slug="suzuki-sv-650", status=MotorbikeStatus.IN_REVIEW
    )
    fake_session.add(existing)

    result = runner.invoke(cli, ["suggestions", "import", str(list_path)])

    assert existing.suggestion is not None
    assert existing.suggestion["year_from"] == 1999
    # Enriching is not a re-run: the row keeps the status it had.
    assert existing.status is MotorbikeStatus.IN_REVIEW
    assert "0 enriched" not in result.output


def test_dry_run_writes_nothing(fake_session: FakeAsyncSession, list_path: Path) -> None:
    result = runner.invoke(cli, ["suggestions", "import", str(list_path), "--dry-run"])

    assert result.exit_code == 0
    assert fake_session.rows(Motorbike) == []
    assert "4 model(s) parsed, nothing written." in result.output


def test_a_missing_list_file_fails_without_writing(
    fake_session: FakeAsyncSession, tmp_path: Path
) -> None:
    result = runner.invoke(cli, ["suggestions", "import", str(tmp_path / "absent.txt")])

    assert result.exit_code == 1
    assert fake_session.rows(Motorbike) == []


def test_a_list_without_a_single_entry_fails(
    fake_session: FakeAsyncSession, tmp_path: Path
) -> None:
    path = tmp_path / "empty.txt"
    path.write_text('[1]: https://example.invalid "nothing here"\n', encoding="utf-8")

    result = runner.invoke(cli, ["suggestions", "import", str(path)])

    assert result.exit_code == 1
    assert fake_session.rows(Motorbike) == []


def test_the_shipped_list_parses_without_a_single_warning() -> None:
    text = suggestions_cli.DEFAULT_LIST_PATH.read_text(encoding="utf-8")

    models, warnings = suggestions_cli.parse_list(text, source="bike-list.txt")

    assert warnings == []
    assert len(models) == 200
    # Every entry is a real proposal: a name plus at least the year it started.
    assert all(model.suggestion["year_from"] is not None for model in models)
    assert json.dumps([model.suggestion for model in models])
