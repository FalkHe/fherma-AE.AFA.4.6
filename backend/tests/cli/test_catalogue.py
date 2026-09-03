"""Tests for `app catalogue set-manufacturer` (step 2b.2).

Same pattern as `tests/cli/test_users.py`: `get_sessionmaker` is monkeypatched on
the CLI module so the real services run against the in-memory `FakeAsyncSession`
from `tests/services/conftest.py` — no engine, no event loop of our own.
"""

import asyncio

import pytest
from typer.testing import CliRunner

from app.cli.main import app as cli
from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.services import manufacturer_service, product_service
from tests.services.conftest import FakeAsyncSession

runner = CliRunner()

SLUG = "suzuki-gsr-600"


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
        "app.cli.catalogue.get_sessionmaker",
        lambda: lambda: _SessionContextManager(fake_session),
    )


@pytest.fixture
def motorbike(fake_session: FakeAsyncSession) -> Motorbike:
    entry = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    fake_session.notifications.clear()
    return entry


@pytest.mark.usefixtures("motorbike")
def test_set_manufacturer_creates_the_brand_and_prints_its_id(
    fake_session: FakeAsyncSession,
) -> None:
    result = runner.invoke(cli, ["catalogue", "set-manufacturer", SLUG, "  Suzuki "])

    assert result.exit_code == 0, result.output
    manufacturer = fake_session.rows(Manufacturer)[0]
    assert (manufacturer.name, manufacturer.slug) == ("Suzuki", "suzuki")
    assert manufacturer.id in result.stdout
    assert "Suzuki" in result.stdout


def test_set_manufacturer_points_the_catalogue_entry_at_the_brand(
    fake_session: FakeAsyncSession, motorbike: Motorbike
) -> None:
    result = runner.invoke(cli, ["catalogue", "set-manufacturer", SLUG, "Suzuki"])

    assert result.exit_code == 0, result.output
    manufacturer = fake_session.rows(Manufacturer)[0]
    assert motorbike.manufacturer_id == manufacturer.id
    # `assign_manufacturer` announces the product, so the backlog re-renders.
    assert [channel for channel, _ in fake_session.notifications] == ["app_events"]


@pytest.mark.usefixtures("motorbike")
def test_rerunning_with_a_differently_spelled_brand_reuses_the_row(
    fake_session: FakeAsyncSession,
) -> None:
    first = runner.invoke(cli, ["catalogue", "set-manufacturer", SLUG, "Suzuki"])
    assert first.exit_code == 0, first.output

    second = runner.invoke(cli, ["catalogue", "set-manufacturer", SLUG, "suzuki"])

    assert second.exit_code == 0, second.output
    assert len(fake_session.rows(Manufacturer)) == 1


def test_an_unknown_slug_exits_one_without_creating_anything(
    fake_session: FakeAsyncSession,
) -> None:
    result = runner.invoke(cli, ["catalogue", "set-manufacturer", "ghost-bike", "Suzuki"])

    assert result.exit_code == 1
    assert "ghost-bike" in result.stderr
    assert result.stdout == ""
    assert fake_session.rows(Manufacturer) == []


def test_a_name_without_an_identity_exits_one_with_a_message(
    fake_session: FakeAsyncSession, motorbike: Motorbike
) -> None:
    """`get_or_create` rejects "???" — the CLI reports it instead of crashing."""
    result = runner.invoke(cli, ["catalogue", "set-manufacturer", SLUG, "???"])

    assert result.exit_code == 1
    assert "???" in result.stderr
    assert fake_session.rows(Manufacturer) == []
    assert motorbike.manufacturer_id is None


@pytest.mark.usefixtures("motorbike")
def test_the_command_never_reaches_the_service_without_a_brand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    async def _spy(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(manufacturer_service, "get_or_create", _spy)

    result = runner.invoke(cli, ["catalogue", "set-manufacturer", SLUG])

    assert result.exit_code != 0
    assert calls == []


# --- `app catalogue render-name` (step 6.11) --------------------------------


def test_render_name_prints_the_query_name_fallback_when_no_identity_exists(
    fake_session: FakeAsyncSession, motorbike: Motorbike
) -> None:
    """No `model_name` is set yet, so both levels fall back to `query_name`."""
    result = runner.invoke(cli, ["catalogue", "render-name", motorbike.id])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        f"MODEL: {motorbike.query_name}",
        f"YEAR_RANGE: {motorbike.query_name}",
    ]


def test_render_name_escalates_against_the_supplied_context(
    fake_session: FakeAsyncSession, motorbike: Motorbike
) -> None:
    manufacturer = asyncio.run(manufacturer_service.get_or_create(fake_session, "BMW"))
    asyncio.run(product_service.assign_manufacturer(fake_session, motorbike, manufacturer.id))
    motorbike.model_name = "R 1250 GS"
    motorbike.year_from = 2019
    motorbike.year_to = 2023

    other = asyncio.run(product_service.create_backlog(fake_session, "BMW R 1250 GS (older)"))
    asyncio.run(product_service.assign_manufacturer(fake_session, other, manufacturer.id))
    other.model_name = "R 1250 GS"
    other.year_from = 2010
    other.year_to = 2013

    result = runner.invoke(cli, ["catalogue", "render-name", motorbike.id, "--context", other.id])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines() == [
        "MODEL: BMW R 1250 GS (2019–2023)",
        "YEAR_RANGE: BMW R 1250 GS (2019–2023)",
    ]


def test_render_name_of_an_unknown_id_exits_one(fake_session: FakeAsyncSession) -> None:
    result = runner.invoke(cli, ["catalogue", "render-name", "01UNKNOWNUNKNOWNUNKNOWN"])

    assert result.exit_code == 1
    assert "01UNKNOWNUNKNOWNUNKNOWN" in result.stderr
    assert result.stdout == ""


# --- `app catalogue set-identity` (step 6.12) -------------------------------


def test_set_identity_happy_path_recomputes_the_canonical_slug(
    fake_session: FakeAsyncSession, motorbike: Motorbike
) -> None:
    result = runner.invoke(
        cli,
        [
            "catalogue",
            "set-identity",
            SLUG,
            "--manufacturer",
            "BMW",
            "--model-name",
            "R 1250 GS",
            "--year-from",
            "2019",
            "--year-to",
            "2023",
            "--buildingline",
            "GS",
            "--type-code",
            "K50",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "bmw/r-1250-gs/2019-2023" in result.stdout
    assert motorbike.slug == "bmw/r-1250-gs/2019-2023"
    assert motorbike.model_name == "R 1250 GS"
    assert motorbike.year_from == 2019
    assert motorbike.year_to == 2023
    assert motorbike.buildingline == "GS"
    assert motorbike.type_codes == ["K50"]
    manufacturer = fake_session.rows(Manufacturer)[0]
    assert manufacturer.name == "BMW"
    assert motorbike.manufacturer_id == manufacturer.id


def test_set_identity_an_unknown_slug_exits_one_without_creating_anything(
    fake_session: FakeAsyncSession,
) -> None:
    result = runner.invoke(
        cli,
        [
            "catalogue",
            "set-identity",
            "ghost-bike",
            "--manufacturer",
            "BMW",
            "--model-name",
            "R 1250 GS",
            "--year-from",
            "2019",
        ],
    )

    assert result.exit_code == 1
    assert "ghost-bike" in result.stderr
    assert result.stdout == ""
    assert fake_session.rows(Manufacturer) == []


def test_set_identity_bad_variants_json_exits_one(
    fake_session: FakeAsyncSession, motorbike: Motorbike
) -> None:
    result = runner.invoke(
        cli,
        [
            "catalogue",
            "set-identity",
            SLUG,
            "--manufacturer",
            "BMW",
            "--model-name",
            "R 1250 GS",
            "--year-from",
            "2019",
            "--variants-json",
            "{not json",
        ],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert motorbike.model_name is None
    assert fake_session.rows(Manufacturer) == []


def test_set_identity_duplicate_slug_exits_one(fake_session: FakeAsyncSession) -> None:
    first = asyncio.run(product_service.create_backlog(fake_session, "BMW R 1250 GS"))
    other = asyncio.run(product_service.create_backlog(fake_session, "R 1250 GS import"))
    args = [
        "--manufacturer",
        "BMW",
        "--model-name",
        "R 1250 GS",
        "--year-from",
        "2019",
        "--year-to",
        "2023",
    ]
    first_result = runner.invoke(cli, ["catalogue", "set-identity", first.slug, *args])
    assert first_result.exit_code == 0, first_result.output

    result = runner.invoke(cli, ["catalogue", "set-identity", other.slug, *args])

    assert result.exit_code == 1
    assert "bmw/r-1250-gs/2019-2023" in result.stderr
    assert other.model_name is None
    assert other.slug != first.slug


# --- `app catalogue backfill-identity` (step 6.18) --------------------------


def test_backfill_identity_strips_the_manufacturer_prefix(
    fake_session: FakeAsyncSession,
) -> None:
    manufacturer = asyncio.run(manufacturer_service.get_or_create(fake_session, "BMW"))
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "BMW S 1000 XR"))
    motorbike.manufacturer_id = manufacturer.id

    result = runner.invoke(cli, ["catalogue", "backfill-identity"])

    assert result.exit_code == 0, result.output
    assert motorbike.model_name == "S 1000 XR"
    assert "S 1000 XR" in result.stdout


def test_backfill_identity_keeps_query_name_verbatim_without_a_prefix_match(
    fake_session: FakeAsyncSession,
) -> None:
    manufacturer = asyncio.run(manufacturer_service.get_or_create(fake_session, "Suzuki"))
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "GSR 600"))
    motorbike.manufacturer_id = manufacturer.id

    result = runner.invoke(cli, ["catalogue", "backfill-identity"])

    assert result.exit_code == 0, result.output
    assert motorbike.model_name == "GSR 600"


def test_backfill_identity_leaves_suggestion_untouched(fake_session: FakeAsyncSession) -> None:
    manufacturer = asyncio.run(manufacturer_service.get_or_create(fake_session, "BMW"))
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "BMW S 1000 XR"))
    motorbike.manufacturer_id = manufacturer.id
    motorbike.suggestion = {"links": ["https://example.invalid"], "year_from": 1999}

    result = runner.invoke(cli, ["catalogue", "backfill-identity"])

    assert result.exit_code == 0, result.output
    assert motorbike.suggestion == {"links": ["https://example.invalid"], "year_from": 1999}


def test_backfill_identity_dry_run_writes_nothing(fake_session: FakeAsyncSession) -> None:
    manufacturer = asyncio.run(manufacturer_service.get_or_create(fake_session, "BMW"))
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "BMW S 1000 XR"))
    motorbike.manufacturer_id = manufacturer.id
    commits_before = fake_session.commit_count

    result = runner.invoke(cli, ["catalogue", "backfill-identity", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert "WOULD SET" in result.stdout
    assert "S 1000 XR" in result.stdout
    assert motorbike.model_name is None
    assert fake_session.commit_count == commits_before


def test_backfill_identity_rows_without_a_manufacturer_are_listed_as_skipped(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Mystery Bike"))

    result = runner.invoke(cli, ["catalogue", "backfill-identity"])

    assert result.exit_code == 0, result.output
    assert f"SKIPPED {motorbike.slug}" in result.stdout
    assert motorbike.model_name is None


def test_backfill_identity_reports_a_collision_and_leaves_the_row(
    fake_session: FakeAsyncSession,
) -> None:
    manufacturer = asyncio.run(manufacturer_service.get_or_create(fake_session, "BMW"))
    first = asyncio.run(product_service.create_backlog(fake_session, "BMW R 1250 GS import 1"))
    first.manufacturer_id = manufacturer.id
    first.year_from = 2019
    first.query_name = "BMW R 1250 GS"
    second = asyncio.run(product_service.create_backlog(fake_session, "BMW R 1250 GS import 2"))
    second.manufacturer_id = manufacturer.id
    second.year_from = 2019
    second.query_name = "BMW R 1250 GS"
    second_original_slug = second.slug

    result = runner.invoke(cli, ["catalogue", "backfill-identity"])

    assert result.exit_code == 0, result.output
    assert first.model_name == "R 1250 GS"
    assert first.slug == "bmw/r-1250-gs/2019-"
    assert "COLLISION" in result.stdout
    assert "bmw/r-1250-gs/2019-" in result.stdout
    assert second.model_name is None
    assert second.slug == second_original_slug


def test_backfill_identity_prints_the_gap_table_and_flags_approved_rows(
    fake_session: FakeAsyncSession,
) -> None:
    backlog_gap = asyncio.run(product_service.create_backlog(fake_session, "Backlog Gap Bike"))
    approved_gap = asyncio.run(product_service.create_backlog(fake_session, "Approved Gap Bike"))
    # Bypass `transition` (the DB CHECK constraint this step also adds is the
    # real guard) to park a row `approved` without a year range, the same way
    # `tests/services/test_product_service.py::_in_status` does.
    approved_gap.status = MotorbikeStatus.APPROVED
    complete = asyncio.run(product_service.create_backlog(fake_session, "Complete Bike"))
    complete.year_from = 2020

    result = runner.invoke(cli, ["catalogue", "backfill-identity"])

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    gap_lines = lines[lines.index("--- Rows still missing a year range ---") + 1 :]
    assert f"{backlog_gap.slug} (backlog)" in gap_lines
    assert f"{approved_gap.slug} (approved) [APPROVED]" in gap_lines
    assert not any(line.startswith(complete.slug) for line in gap_lines)
