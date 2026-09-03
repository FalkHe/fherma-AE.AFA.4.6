"""Table-driven proof of `naming_service`'s escalation algorithm (step 6.11).

Every row either encodes one of `docs/model-naming.md`'s own example strings
(cited in the test name / docstring) or exercises one step of
`docs/roadmap/model-naming-data-model.md` §5's six-step algorithm. No test
here touches a database — `render_name`/`render_names`/`render_buildingline`
are pure; `load_name_parts` is covered separately against `FakeAsyncSession`.
"""

import asyncio
import logging

import pytest

from app.services import manufacturer_service, product_service
from app.services.naming_service import (
    NameLevel,
    NameParts,
    load_name_parts,
    render_buildingline,
    render_name,
    render_names,
)
from tests.services.conftest import FakeAsyncSession


def _parts(
    motorbike_id: str = "01ID",
    *,
    manufacturer: str | None = "BMW",
    buildingline: str | None = None,
    model_name: str | None = "R 1250 GS",
    year_from: int | None = None,
    year_to: int | None = None,
    query_name: str = "BMW R 1250 GS",
) -> NameParts:
    return NameParts(
        motorbike_id=motorbike_id,
        manufacturer=manufacturer,
        buildingline=buildingline,
        model_name=model_name,
        year_from=year_from,
        year_to=year_to,
        query_name=query_name,
    )


# --- docs/model-naming.md's own example rows -------------------------------


def test_kawasaki_z900_matches_the_examples_table() -> None:
    """`docs/model-naming.md` "Examples": `Kawasaki | Kawasaki Z900 (2020–2024)`."""
    parts = _parts(manufacturer="Kawasaki", model_name="Z900", year_from=2020, year_to=2024)

    assert render_name(parts, min_level=NameLevel.YEAR_RANGE) == "Kawasaki Z900 (2020–2024)"


def test_ducati_multistrada_matches_the_examples_table() -> None:
    """`docs/model-naming.md` "Examples": `Ducati | Ducati Multistrada V4 S (2021–2024)`."""
    parts = _parts(
        manufacturer="Ducati", model_name="Multistrada V4 S", year_from=2021, year_to=2024
    )

    assert (
        render_name(parts, min_level=NameLevel.YEAR_RANGE) == "Ducati Multistrada V4 S (2021–2024)"
    )


def test_bmw_r1250gs_matches_the_year_range_table() -> None:
    """`docs/model-naming.md` "Year range instead of a single year": `BMW R 1250 GS (2019–2023)`."""
    parts = _parts(model_name="R 1250 GS", year_from=2019, year_to=2023)

    assert render_name(parts, min_level=NameLevel.YEAR_RANGE) == "BMW R 1250 GS (2019–2023)"


# --- Algorithm step 1: the query_name fallback ------------------------------


def test_no_model_name_falls_back_to_query_name_verbatim() -> None:
    """Step 1: `model_name is None` returns `query_name` verbatim, never an error."""
    parts = _parts(model_name=None, query_name="  Suzuki GSR 600 (free text) ")

    assert render_name(parts) == "  Suzuki GSR 600 (free text) "


def test_the_fallback_ignores_context_and_min_level() -> None:
    """The fallback short-circuits before ambiguity or level are ever considered."""
    parts = _parts(model_name=None, query_name="Custom Entry")
    other = _parts("01OTHER", query_name="Custom Entry")

    assert render_name(parts, context=[other], min_level=NameLevel.YEAR_RANGE) == "Custom Entry"


# --- Algorithm step 2: no-context render at each min_level ------------------


def test_no_context_renders_at_model_level_by_default() -> None:
    parts = _parts(model_name="R 1300 GS", year_from=2023, year_to=None)

    assert render_name(parts) == "BMW R 1300 GS"


def test_no_context_renders_at_the_requested_min_level() -> None:
    parts = _parts(model_name="R 1300 GS", year_from=2023, year_to=None)

    assert render_name(parts, min_level=NameLevel.YEAR_RANGE) == "BMW R 1300 GS (from 2023)"


def test_buildingline_min_level_still_floors_at_model() -> None:
    """Step 2: "start at `max(MODEL, min_level)`" — BUILDINGLINE never wins."""
    parts = _parts(model_name="R 1300 GS")

    assert render_name(parts, min_level=NameLevel.BUILDINGLINE) == "BMW R 1300 GS"


# --- Algorithm steps 3-4: escalation only for the colliding subset ---------


def test_escalation_only_touches_the_colliding_subset() -> None:
    """Three rows, two colliding at MODEL level: the third stays short (step 4)."""
    older_gs = _parts("01OLDER", model_name="R 1250 GS", year_from=2010, year_to=2013)
    newer_gs = _parts("01NEWER", model_name="R 1250 GS", year_from=2019, year_to=2023)
    unrelated = _parts("01OTHER", model_name="R 1300 GS", year_from=2023, year_to=None)
    context = [older_gs, newer_gs, unrelated]

    assert render_name(older_gs, context=context) == "BMW R 1250 GS (2010–2013)"
    assert render_name(newer_gs, context=context) == "BMW R 1250 GS (2019–2023)"
    # Not ambiguous at MODEL level against either of the others: stays short.
    assert render_name(unrelated, context=context) == "BMW R 1300 GS"


def test_a_context_member_with_the_same_id_never_causes_a_collision() -> None:
    """Ambiguity requires "a different `motorbike_id`" — self-in-context is a no-op."""
    parts = _parts(model_name="R 1300 GS")

    assert render_name(parts, context=[parts]) == "BMW R 1300 GS"


def test_render_at_year_range_level_is_not_ambiguous_when_years_differ() -> None:
    a = _parts("01A", model_name="R 1250 GS", year_from=2010, year_to=2013)
    b = _parts("01B", model_name="R 1250 GS", year_from=2019, year_to=2023)

    assert (
        render_name(a, context=[b], min_level=NameLevel.YEAR_RANGE) == "BMW R 1250 GS (2010–2013)"
    )


# --- Algorithm step 5: year-range spellings ---------------------------------


def test_open_year_range_renders_from_year() -> None:
    parts = _parts(model_name="R 1300 GS", year_from=2023, year_to=None)

    assert render_name(parts, min_level=NameLevel.YEAR_RANGE) == "BMW R 1300 GS (from 2023)"


def test_missing_year_from_skips_the_year_segment_entirely() -> None:
    """Step 5: "skipped when `year_from is None`" — even when `year_to` is set."""
    parts = _parts(model_name="R 1300 GS", year_from=None, year_to=2024)

    assert render_name(parts, min_level=NameLevel.YEAR_RANGE) == "BMW R 1300 GS"


# --- Algorithm step 6: the id-suffix last resort ----------------------------


def test_a_genuine_duplicate_identity_appends_the_id_suffix_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Step 6: identical manufacturer/model/year range on two rows is a data bug."""
    first = _parts(
        "01AAAAAAAAAAAAAAAAAAAAAAAAA", model_name="R 1250 GS", year_from=2019, year_to=2023
    )
    second = _parts(
        "01BBBBBBBBBBBBBBBBBBBBBBBBB", model_name="R 1250 GS", year_from=2019, year_to=2023
    )

    with caplog.at_level(logging.WARNING, logger="app.services.naming_service"):
        rendered = render_name(first, context=[second])

    assert rendered == f"BMW R 1250 GS (2019–2023) [{first.motorbike_id[-6:]}]"
    assert any("still collides" in record.message for record in caplog.records)


# --- render_names: mutual context --------------------------------------------


def test_render_names_uses_every_other_member_as_context() -> None:
    older_gs = _parts("01OLDER", model_name="R 1250 GS", year_from=2010, year_to=2013)
    newer_gs = _parts("01NEWER", model_name="R 1250 GS", year_from=2019, year_to=2023)
    unrelated = _parts("01OTHER", model_name="R 1300 GS", year_from=2023, year_to=None)

    rendered = render_names([older_gs, newer_gs, unrelated])

    assert rendered == {
        "01OLDER": "BMW R 1250 GS (2010–2013)",
        "01NEWER": "BMW R 1250 GS (2019–2023)",
        "01OTHER": "BMW R 1300 GS",
    }


def test_render_names_at_year_range_min_level() -> None:
    a = _parts("01A", model_name="R 1300 GS", year_from=2023, year_to=None)

    assert render_names([a], min_level=NameLevel.YEAR_RANGE) == {"01A": "BMW R 1300 GS (from 2023)"}


# --- render_buildingline: level 0, headings/facets only ---------------------


def test_render_buildingline_matches_the_data_model_example() -> None:
    """`docs/model-naming.md` Examples table's own group heading: `BMW GS`."""
    parts = _parts(buildingline="GS")

    assert render_buildingline(parts) == "BMW GS"


def test_render_buildingline_is_none_without_one() -> None:
    parts = _parts(buildingline=None)

    assert render_buildingline(parts) is None


# --- load_name_parts: the batched read, two selects, no ORM relationships --


def test_load_name_parts_batches_the_manufacturer_lookup(fake_session: FakeAsyncSession) -> None:
    async def _setup() -> tuple[str, str]:
        manufacturer = await manufacturer_service.get_or_create(fake_session, "BMW")
        motorbike = await product_service.create_backlog(fake_session, "BMW R 1250 GS")
        await product_service.assign_manufacturer(fake_session, motorbike, manufacturer.id)
        motorbike.model_name = "R 1250 GS"
        motorbike.year_from = 2019
        motorbike.year_to = 2023
        return motorbike.id, manufacturer.id

    motorbike_id, _manufacturer_id = asyncio.run(_setup())

    parts = asyncio.run(load_name_parts(fake_session, [motorbike_id]))

    assert parts.keys() == {motorbike_id}
    result = parts[motorbike_id]
    assert result.manufacturer == "BMW"
    assert (result.model_name, result.year_from, result.year_to) == ("R 1250 GS", 2019, 2023)
    assert result.query_name == "BMW R 1250 GS"


def test_load_name_parts_leaves_manufacturer_none_when_unassigned(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))

    parts = asyncio.run(load_name_parts(fake_session, [motorbike.id]))

    assert parts[motorbike.id].manufacturer is None


def test_load_name_parts_omits_unknown_ids_instead_of_raising(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))

    parts = asyncio.run(load_name_parts(fake_session, [motorbike.id, "01UNKNOWNUNKNOWNUNKNOWN"]))

    assert parts.keys() == {motorbike.id}


def test_load_name_parts_of_an_empty_sequence_returns_empty_without_a_query(
    fake_session: FakeAsyncSession,
) -> None:
    assert asyncio.run(load_name_parts(fake_session, [])) == {}
