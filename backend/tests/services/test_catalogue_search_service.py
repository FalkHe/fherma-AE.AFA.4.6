"""`app/services/catalogue_search_service.py` — the shortlist SQL (step 3.8).

The statement joins two tables and is executed by PostgreSQL, which no test here
connects to (see `tests/conftest.py`), and the service-level `FakeAsyncSession`
interprets single-entity selects only — so the convention established in
`test_retrieval_service.py` applies: a `RecordingSession` replays scripted rows
and the **compiled** SQL is what is asserted.

What matters about this service is entirely in that statement:

* the two non-negotiable conditions (`approved` entry, `verified` revision);
* one clause per stated bound, on the right column, with the value bound rather
  than inlined;
* no clause at all for a bound the customer did not state — and, crucially, no
  Python-side post-filtering that would let an unverified value decide a match.
"""

import asyncio
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models.motorbike import MotorbikeStatus
from app.db.models.motorbike_spec import SPEC_FIELDS, SpecKind
from app.llm.query_translation import FILTER_FIELD_COLUMNS, SpecFilters
from app.services import catalogue_search_service

BIKE_ID = "01J0BIKE00000000000000000A"
OTHER_BIKE_ID = "01J0BIKE00000000000000000B"

# `%(name)s` placeholders make an assertion depend on SQLAlchemy's parameter
# numbering; the shape of the statement is what matters here.
_PARAMETER = re.compile(r"%\([a-z_0-9]+\)s")

# One plausible answer per field of `SpecFilters`, so the coverage test below can
# drive every bound. Asserted to be complete: a new bound without a sample here
# fails instead of going untested.
SAMPLES: dict[str, Any] = {
    "categories": ["naked", "scrambler"],
    "engine_cc_min": 400,
    "engine_cc_max": 800,
    "power_kw_min": 20.0,
    "power_kw_max": 35.0,
    "wet_weight_kg_max": 200.0,
    "seat_height_mm_max": 800,
    "a2_eligible": True,
    "price_bands": ["budget", "mid"],
}


class _Scalars:
    def __init__(self, rows: list[str]) -> None:
        self._rows = rows

    def all(self) -> list[str]:
        return self._rows


class _Result:
    def __init__(self, rows: list[str]) -> None:
        self._rows = rows

    def scalars(self) -> _Scalars:
        return _Scalars(self._rows)


class RecordingSession:
    """Stands in for `AsyncSession`: records statements, replays scripted ids."""

    def __init__(self, rows: list[str] | None = None) -> None:
        self.rows = rows if rows is not None else []
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        return _Result(self.rows)


def _find(session: RecordingSession, filters: SpecFilters | None = None) -> list[str]:
    """Drive the async service from a synchronous test."""
    return asyncio.run(
        catalogue_search_service.find_motorbike_ids(session, filters or SpecFilters())
    )


def _compiled(session: RecordingSession) -> Any:
    """Compile the single statement the service issued, for PostgreSQL."""
    assert len(session.statements) == 1, "a shortlist must be one round trip"
    return session.statements[0].compile(dialect=postgresql.dialect())


def _sql(session: RecordingSession) -> str:
    """Return the compiled SQL with bound parameters reduced to `?`."""
    return _PARAMETER.sub("?", str(_compiled(session)))


def test_returns_the_ids_the_database_returned_in_its_order() -> None:
    """The service maps, it does not sort or filter."""
    session = RecordingSession([BIKE_ID, OTHER_BIKE_ID])

    assert _find(session) == [BIKE_ID, OTHER_BIKE_ID]


def test_only_verified_specs_of_approved_models_are_searched() -> None:
    """The two conditions that make a number showable, both in SQL."""
    session = RecordingSession()

    _find(session)
    sql = _sql(session)
    params = _compiled(session).params

    assert "JOIN motorbike_specs ON motorbike_specs.motorbike_id = motorbikes.id" in sql
    assert "motorbikes.status = ?" in sql
    assert "motorbike_specs.kind = ?" in sql
    assert params["status_1"] is MotorbikeStatus.APPROVED
    assert params["kind_1"] is SpecKind.VERIFIED
    # A stable order the caller can cut without re-sorting.
    assert "ORDER BY motorbikes.query_name, motorbikes.id" in sql


def test_an_empty_filter_set_narrows_nothing() -> None:
    """No stated bound, no clause — the whole approved candidate space."""
    session = RecordingSession()

    _find(session)
    sql = _sql(session)

    for column in set(FILTER_FIELD_COLUMNS.values()):
        assert f"motorbike_specs.{column} " not in sql


def test_every_sample_covers_a_field_of_the_filter_schema() -> None:
    """The coverage test below is only as complete as this table."""
    assert set(SAMPLES) == set(SpecFilters.model_fields)


@pytest.mark.parametrize("field", sorted(SAMPLES))
def test_every_stated_bound_becomes_a_clause_on_its_column(field: str) -> None:
    """One bound in, one clause on the frozen column it constrains."""
    session = RecordingSession()

    _find(session, SpecFilters.model_validate({field: SAMPLES[field]}))
    sql = _sql(session)

    column = f"motorbike_specs.{FILTER_FIELD_COLUMNS[field]}"
    assert column in sql
    # Every other filterable column stays out of the statement.
    for other in set(FILTER_FIELD_COLUMNS.values()) - {FILTER_FIELD_COLUMNS[field]}:
        assert f"motorbike_specs.{other} " not in sql


def test_the_bounds_are_the_expected_comparisons() -> None:
    """Minima are `>=`, maxima are `<=`, vocabularies are `IN`, A2 is `IS`."""
    session = RecordingSession()

    _find(session, SpecFilters.model_validate(SAMPLES))
    sql = _sql(session)
    params = _compiled(session).params

    assert "motorbike_specs.engine_cc >= ?" in sql
    assert "motorbike_specs.engine_cc <= ?" in sql
    assert "motorbike_specs.power_kw >= ?" in sql
    assert "motorbike_specs.power_kw <= ?" in sql
    assert "motorbike_specs.wet_weight_kg <= ?" in sql
    assert "motorbike_specs.seat_height_mm <= ?" in sql
    # `IS true`, so a bike whose eligibility is unknown never passes.
    assert "motorbike_specs.a2_eligible IS true" in sql
    assert "motorbike_specs.category IN (__[POSTCOMPILE_category_1])" in sql
    assert "motorbike_specs.price_band IN (__[POSTCOMPILE_price_band_1])" in sql
    # Enum members are unwrapped: the columns are `String`, not enums.
    assert params["category_1"] == ["naked", "scrambler"]
    assert params["price_band_1"] == ["budget", "mid"]
    assert params["seat_height_mm_1"] == 800


def test_a2_eligible_false_is_a_clause_too() -> None:
    """`False` is a stated bound, not "unstated" — and `NULL` still never passes."""
    session = RecordingSession()

    _find(session, SpecFilters(a2_eligible=False))

    assert "motorbike_specs.a2_eligible IS false" in _sql(session)


# --- step 3.11: shared name resolution and the comparison projection ----------
#
# Same convention as above: no database, the **compiled** statement is what is
# asserted. `resolve_name` issues up to two statements (the slug lookup through
# `product_service`, then the substring fallback) and `get_verified_specs` one
# outer join, so these tests use a session that replays a *queue* of results.


@dataclass(frozen=True, slots=True)
class _Motorbike:
    """The three attributes the resolver and the projection read."""

    id: str
    query_name: str
    status: MotorbikeStatus


class _ScriptedScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows

    def first(self) -> Any | None:
        return self._rows[0] if self._rows else None


class _ScriptedResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> Any | None:
        assert len(self._rows) <= 1
        return self._rows[0] if self._rows else None

    def scalars(self) -> _ScriptedScalars:
        return _ScriptedScalars(self._rows)

    def mappings(self) -> _ScriptedScalars:
        return _ScriptedScalars(self._rows)


class ScriptedSession:
    """Records statements and replays one scripted result set per `execute`."""

    def __init__(self, *results: list[Any]) -> None:
        self.results = list(results)
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _ScriptedResult:
        self.statements.append(statement)
        return _ScriptedResult(self.results.pop(0) if self.results else [])


def _sql_at(session: ScriptedSession, index: int) -> str:
    """Return one recorded statement's compiled SQL, parameters reduced to `?`."""
    return _PARAMETER.sub("?", str(session.statements[index].compile(dialect=postgresql.dialect())))


def _params_at(session: ScriptedSession, index: int) -> dict[str, Any]:
    return dict(session.statements[index].compile(dialect=postgresql.dialect()).params)


def _resolve(session: ScriptedSession, name: str) -> Any | None:
    """Drive the async resolver from a synchronous test."""
    return asyncio.run(catalogue_search_service.resolve_name(session, name))


def _verified(session: ScriptedSession, motorbike_ids: list[str]) -> list[Any]:
    """Drive the async projection from a synchronous test."""
    return asyncio.run(catalogue_search_service.get_verified_specs(session, motorbike_ids))


def test_an_exact_slug_match_wins_before_any_substring_search() -> None:
    """Resolution order: the slug is the identity, everything else is a guess."""
    approved = _Motorbike(BIKE_ID, "Honda CB500F", MotorbikeStatus.APPROVED)
    session = ScriptedSession(
        [approved], [_Motorbike(OTHER_BIKE_ID, "x", MotorbikeStatus.APPROVED)]
    )

    assert _resolve(session, "  Honda   CB500F ") is approved
    # One statement: neither the type-code nor the substring leg ever ran.
    assert len(session.statements) == 1
    assert _params_at(session, 0)["slug_1"] == "honda-cb500f"


def test_a_single_type_code_hit_wins_before_the_substring_search() -> None:
    """A code the slug leg missed, matched exactly once, is precise enough to trust."""
    approved = _Motorbike(BIKE_ID, "Suzuki GSR600", MotorbikeStatus.APPROVED)
    session = ScriptedSession([], [approved])

    assert _resolve(session, "wvb9") is approved
    # Two statements: the slug leg missed, the code leg answered — the
    # substring leg never ran.
    assert len(session.statements) == 2
    sql = _sql_at(session, 1)
    params = _params_at(session, 1)
    assert "motorbikes.status = ?" in sql
    assert params["status_1"] is MotorbikeStatus.APPROVED
    # Upper-cased and trimmed before it is matched, against the typed column…
    assert "motorbikes.type_codes @> ?::JSONB" in sql
    assert params["type_codes_1"] == ["WVB9"]
    # …or, as a retrieval hint only (D6), against the unverified claim.
    assert "motorbikes.suggestion[?] @> ?::JSONB" in sql
    assert params["suggestion_1"] == "type_codes"
    assert params["param_1"] == ["WVB9"]


def test_an_ambiguous_type_code_falls_through_rather_than_guessing() -> None:
    """Several rows claiming the same code is a question, not an answer."""
    approved = _Motorbike(BIKE_ID, "Honda CB500F", MotorbikeStatus.APPROVED)
    two_codes = [
        _Motorbike(BIKE_ID, "x", MotorbikeStatus.APPROVED),
        _Motorbike(OTHER_BIKE_ID, "y", MotorbikeStatus.APPROVED),
    ]
    session = ScriptedSession([], two_codes, [approved])

    assert _resolve(session, "PC46") is approved
    # All three legs ran: the ambiguous code fell through to the substring.
    assert len(session.statements) == 3


def test_a_type_code_with_no_hit_falls_through_to_the_substring_leg() -> None:
    """None matching is a miss, not a guess — same fall-through as ambiguous."""
    approved = _Motorbike(BIKE_ID, "Honda CB500F", MotorbikeStatus.APPROVED)
    session = ScriptedSession([], [], [approved])

    assert _resolve(session, "CB500F") is approved
    assert len(session.statements) == 3


def test_a_name_the_earlier_legs_miss_falls_through_to_an_approved_substring_match() -> None:
    """ "CB500F" is not a slug or a code, so step three has to find the entry."""
    approved = _Motorbike(BIKE_ID, "Honda CB500F", MotorbikeStatus.APPROVED)
    session = ScriptedSession([], [], [approved])

    assert _resolve(session, "CB500F") is approved
    sql = _sql_at(session, 2)
    params = _params_at(session, 2)
    assert "motorbikes.query_name ILIKE ?" in sql
    assert "motorbikes.model_name ILIKE ?" in sql
    assert params["query_name_1"] == "%CB500F%"
    assert params["model_name_1"] == "%CB500F%"
    # Approved only, shortest name first, one answer.
    assert "motorbikes.status = ?" in sql
    assert params["status_1"] is MotorbikeStatus.APPROVED
    assert (
        "ORDER BY least(char_length(motorbikes.query_name), "
        "coalesce(char_length(motorbikes.model_name), ?)), "
        "motorbikes.query_name, motorbikes.id" in sql
    )
    assert params["coalesce_1"] == 32767
    assert "LIMIT ?" in sql


def test_a_slug_hit_that_is_not_approved_is_not_an_answer() -> None:
    """An unreviewed entry is not showable, so resolution continues and then fails."""
    session = ScriptedSession(
        [_Motorbike(BIKE_ID, "Honda CB500F", MotorbikeStatus.BACKLOG)], [], []
    )

    assert _resolve(session, "Honda CB500F") is None
    # It tried the type-code and the substring legs before giving up.
    assert len(session.statements) == 3


def test_an_unknown_name_resolves_to_none_instead_of_raising() -> None:
    """The pinned contract: tools turn `None` into `{"unknownBike": …}`."""
    session = ScriptedSession([], [], [])

    assert _resolve(session, "Bikeley 999") is None


def test_a_blank_name_is_answered_without_a_single_statement() -> None:
    """Nothing to look up, nothing to ask the database."""
    session = ScriptedSession()

    assert _resolve(session, "   ") is None
    assert session.statements == []


def test_like_wildcards_in_a_name_are_escaped_not_honoured() -> None:
    """A `%` a customer typed must not widen the match to the whole catalogue."""
    session = ScriptedSession([], [], [])

    _resolve(session, "100% naked_bike")

    assert _params_at(session, 2)["query_name_1"] == "%100\\% naked\\_bike%"
    assert _params_at(session, 2)["model_name_1"] == "%100\\% naked\\_bike%"
    assert "ESCAPE '\\\\'" in _sql_at(session, 2)


def test_the_comparable_columns_are_exactly_the_frozen_set_minus_the_long_tail() -> None:
    """Drift guard: a new specification column forces a decision here.

    Same shape as 3.8's guard on the filterable set — a frozen column that is
    neither comparable nor deliberately excluded would silently never appear in a
    comparison table.
    """
    comparable = catalogue_search_service.COMPARISON_SPEC_FIELDS
    excluded = catalogue_search_service.UNCOMPARED_SPEC_FIELDS

    assert set(comparable) | set(excluded) == set(SPEC_FIELDS)
    assert not set(comparable) & set(excluded)
    # Table order follows the frozen column order, so the table is stable.
    assert list(comparable) == [field for field in SPEC_FIELDS if field not in excluded]


def test_the_comparison_projection_is_one_outer_join_over_approved_entries() -> None:
    """The `verified` condition belongs in the `ON` clause, not the `WHERE`.

    In the `WHERE` it would drop an approved entry whose specification was never
    verified — exactly the column a comparison must still be able to show, all
    values `NULL`.
    """
    session = ScriptedSession([])

    _verified(session, [BIKE_ID, OTHER_BIKE_ID])
    sql = _sql_at(session, 0)
    params = _params_at(session, 0)

    assert "LEFT OUTER JOIN motorbike_specs ON motorbike_specs.motorbike_id = motorbikes.id" in sql
    assert "AND motorbike_specs.kind = ?" in sql
    assert params["kind_1"] is SpecKind.VERIFIED
    # The naming parts' manufacturer name is joined in too (step 6.19).
    assert "LEFT OUTER JOIN manufacturers ON manufacturers.id = motorbikes.manufacturer_id" in sql
    assert "motorbikes.status = ?" in sql
    assert params["status_1"] is MotorbikeStatus.APPROVED
    assert "motorbikes.id IN (__[POSTCOMPILE_id_1])" in sql
    # Every comparable column is projected, and nothing else from the spec row.
    for field in catalogue_search_service.COMPARISON_SPEC_FIELDS:
        assert f"motorbike_specs.{field}" in sql
    for field in catalogue_search_service.UNCOMPARED_SPEC_FIELDS:
        assert f"motorbike_specs.{field}" not in sql


def _specs_row(**values: Any) -> dict[str, Any]:
    """One `_specs_statement` row as the database mapping would hand it over.

    Carries the naming columns (buildingline/model_name/year_from/year_to plus
    the joined-in `manufacturer_name`) alongside the comparable spec fields, so
    a `VerifiedSpecs.parts` can always be built without a `KeyError`.
    """
    return (
        {
            "id": BIKE_ID,
            "query_name": "Honda CB500F",
            "buildingline": None,
            "model_name": None,
            "year_from": None,
            "year_to": None,
            "manufacturer_name": None,
        }
        | dict.fromkeys(catalogue_search_service.COMPARISON_SPEC_FIELDS)
        | values
    )


def test_the_comparison_projection_keeps_the_requested_order_and_plain_values() -> None:
    """Alignment is the caller's order; `Decimal` is unwrapped for JSON.

    The database answers in its own order and knows nothing about an unknown id;
    both are the service's problem, and a missing verified row stays `None`.
    """
    rows = [
        _specs_row(id=OTHER_BIKE_ID, query_name="Suzuki GSR600"),
        _specs_row(
            id=BIKE_ID,
            query_name="Honda CB500F",
            power_kw=Decimal("35.0"),
            seat_height_mm=785,
            category="naked",
        ),
    ]
    session = ScriptedSession(rows)

    entries = _verified(session, [BIKE_ID, OTHER_BIKE_ID, "01J0BIKE00000000000000000Z"])

    assert [entry.motorbike_id for entry in entries] == [BIKE_ID, OTHER_BIKE_ID]
    assert entries[0].name == "Honda CB500F"
    assert entries[0].values["power_kw"] == 35.0
    assert isinstance(entries[0].values["power_kw"], float)
    assert entries[0].values["seat_height_mm"] == 785
    # Every comparable field is present, unknown ones explicitly `None`.
    assert set(entries[0].values) == set(catalogue_search_service.COMPARISON_SPEC_FIELDS)
    assert entries[0].values["msrp_eur"] is None
    assert all(value is None for value in entries[1].values.values())
    # `parts` is loaded in the same statement — no extra round trip — and the
    # convenience `name` is `render_name(parts)` for a caller with no context.
    assert entries[0].parts.motorbike_id == BIKE_ID
    assert entries[0].parts.query_name == "Honda CB500F"


def test_a_rendered_name_escalates_only_against_its_own_context() -> None:
    """`VerifiedSpecs.parts` carries enough for a caller to build its own context.

    This is the no-context convenience `name` staying short even when the
    caller (not this projection) would have to escalate for a page of two.
    """
    rows = [
        _specs_row(
            id=BIKE_ID,
            query_name="BMW R 1250 GS 2019",
            model_name="R 1250 GS",
            manufacturer_name="BMW",
            year_from=2019,
            year_to=2023,
        ),
        _specs_row(
            id=OTHER_BIKE_ID,
            query_name="BMW R 1250 GS 2023",
            model_name="R 1250 GS",
            manufacturer_name="BMW",
            year_from=2023,
            year_to=None,
        ),
    ]
    session = ScriptedSession(rows)

    entries = _verified(session, [BIKE_ID, OTHER_BIKE_ID])

    # No context passed to `get_verified_specs` itself, so the convenience
    # `name` never escalates here — that is the caller's job (D5).
    assert entries[0].name == "BMW R 1250 GS"
    assert entries[1].name == "BMW R 1250 GS"


def test_no_ids_means_no_round_trip() -> None:
    """An empty comparison is answered without asking the database."""
    session = ScriptedSession()

    assert _verified(session, []) == []
    assert session.statements == []


# --- step 4.3: the customer browse page --------------------------------------
#
# Same convention once more — no database, the compiled statements are what is
# asserted. `browse_motorbikes` issues exactly two: the count first, then the
# page, so the session below replays a scalar and then a set of mappings.

MANUFACTURER_ID = "01J0MANU00000000000000000A"

BrowseSort = catalogue_search_service.BrowseSort

# The four pinned orderings, spelled exactly as they must compile. `name` is
# the composite brand → model → year-range (step 6.19): a customer catalogue
# has no display column to sort on any more.
BROWSE_ORDERINGS = {
    BrowseSort.NAME: (
        "ORDER BY manufacturers.name ASC NULLS LAST, "
        "motorbikes.model_name ASC NULLS LAST, "
        "motorbikes.year_from ASC NULLS LAST, motorbikes.id ASC"
    ),
    BrowseSort.NAME_DESC: (
        "ORDER BY manufacturers.name DESC NULLS LAST, "
        "motorbikes.model_name DESC NULLS LAST, motorbikes.id ASC"
    ),
    BrowseSort.MSRP_EUR: (
        "ORDER BY motorbike_specs.msrp_eur ASC NULLS LAST, "
        "motorbikes.query_name ASC, motorbikes.id ASC"
    ),
    BrowseSort.MSRP_EUR_DESC: (
        "ORDER BY motorbike_specs.msrp_eur DESC NULLS LAST, "
        "motorbikes.query_name ASC, motorbikes.id ASC"
    ),
}


class _CountResult:
    def __init__(self, total: int) -> None:
        self._total = total

    def scalar_one(self) -> int:
        return self._total


class BrowseSession:
    """Replays the count, then the page; records both statements."""

    def __init__(self, total: int = 0, rows: list[Any] | None = None) -> None:
        self.total = total
        self.rows = rows if rows is not None else []
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        return _CountResult(self.total) if len(self.statements) == 1 else _ScriptedResult(self.rows)


def _browse(
    session: BrowseSession,
    filters: SpecFilters | None = None,
    *,
    manufacturer_ids: list[str] | None = None,
    sort: Any = BrowseSort.NAME,
    limit: int = 24,
    offset: int = 0,
) -> tuple[list[Any], int]:
    """Drive the async browse read from a synchronous test."""
    return asyncio.run(
        catalogue_search_service.browse_motorbikes(
            session,
            filters=filters or SpecFilters(),
            manufacturer_ids=manufacturer_ids,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    )


def _browse_row(**values: Any) -> dict[str, Any]:
    """One page row as the database mapping would hand it over.

    Carries the naming columns (buildingline/model_name/year_from/year_to plus
    the joined-in `manufacturer_name`) alongside the summary spec fields, so a
    `BrowseRow.parts` can always be built without a `KeyError`.
    """
    return (
        {
            "id": BIKE_ID,
            "query_name": "Honda CB500F",
            "manufacturer_id": MANUFACTURER_ID,
            "buildingline": None,
            "model_name": None,
            "year_from": None,
            "year_to": None,
            "manufacturer_name": None,
        }
        | dict.fromkeys(catalogue_search_service.SUMMARY_SPEC_FIELDS)
        | values
    )


def test_the_summary_columns_are_a_subset_of_the_comparable_ones() -> None:
    """Drift guard: a card shows fewer specs than a comparison, never other ones.

    A summary field that is not comparable would be a second, unreviewed
    definition of "a specification value we show a customer".
    """
    summary = catalogue_search_service.SUMMARY_SPEC_FIELDS
    comparable = catalogue_search_service.COMPARISON_SPEC_FIELDS

    assert set(summary) <= set(comparable)
    # Frozen column order, so the projection and the card stay aligned.
    assert list(summary) == [field for field in comparable if field in set(summary)]


def test_a_browse_page_is_one_count_and_one_page_statement() -> None:
    """Two round trips, and the count is not a page (no LIMIT/OFFSET on it)."""
    session = BrowseSession(total=7)

    _, total = _browse(session)

    assert len(session.statements) == 2
    assert total == 7
    count_sql = _sql_at(session, 0)
    assert "count(*)" in count_sql
    assert "LIMIT" not in count_sql
    assert "OFFSET" not in count_sql
    page_sql = _sql_at(session, 1)
    assert "LIMIT ?" in page_sql
    assert "OFFSET ?" in page_sql


def test_browsing_outer_joins_the_verified_specification() -> None:
    """The pinned NULL-spec browse rule, in both statements.

    Deliberately *not* `find_motorbike_ids`' inner join: unfiltered browsing has
    to include an approved model that has no verified revision at all, and the
    `verified` condition therefore belongs in the `ON` clause.
    """
    session = BrowseSession()

    _browse(session)

    for index in (0, 1):
        sql = _sql_at(session, index)
        assert (
            "LEFT OUTER JOIN motorbike_specs ON motorbike_specs.motorbike_id = motorbikes.id "
            "AND motorbike_specs.kind = ?" in sql
        )
        # Both browse statements share the manufacturer join too (step 6.19) —
        # the count is unaffected, since the FK is to-one and cannot multiply
        # a row.
        assert (
            "LEFT OUTER JOIN manufacturers ON manufacturers.id = motorbikes.manufacturer_id" in sql
        )
        assert "motorbikes.status = ?" in sql
        params = _params_at(session, index)
        assert params["kind_1"] is SpecKind.VERIFIED
        assert params["status_1"] is MotorbikeStatus.APPROVED


def test_an_unfiltered_browse_states_no_bound_at_all() -> None:
    """No filter, no clause — every approved model, verified specs or not."""
    session = BrowseSession()

    _browse(session)
    sql = _sql_at(session, 1)

    for column in set(FILTER_FIELD_COLUMNS.values()):
        assert f"motorbike_specs.{column} " not in sql
    assert "motorbikes.manufacturer_id" not in sql.split("WHERE")[1]


def test_browsing_reuses_the_shared_filter_clauses_verbatim() -> None:
    """The one filter vocabulary: browse emits `_clauses`, it restates nothing.

    Each clause is compiled on its own and must appear literally in the browse
    statement — a second, subtly different bound here would be invisible to the
    3.8 tests that guard the advisor's shortlist.
    """
    filters = SpecFilters.model_validate(SAMPLES)
    session = BrowseSession()

    _browse(session, filters)
    sql = _sql_at(session, 1)

    clauses = catalogue_search_service._clauses(filters)
    assert len(clauses) == 9
    for clause in clauses:
        assert _PARAMETER.sub("?", str(clause.compile(dialect=postgresql.dialect()))) in sql


def test_a_manufacturer_filter_is_a_clause_on_the_catalogue_row() -> None:
    """Manufacturer is an identity on `motorbikes`, not a specification value."""
    session = BrowseSession()

    _browse(session, manufacturer_ids=[MANUFACTURER_ID])

    for index in (0, 1):
        assert "motorbikes.manufacturer_id IN (__[POSTCOMPILE_manufacturer_id_1])" in _sql_at(
            session, index
        )
        assert _params_at(session, index)["manufacturer_id_1"] == [MANUFACTURER_ID]


def test_an_empty_manufacturer_set_is_not_a_filter() -> None:
    """`None` and `[]` both mean "unfiltered", as in `list_motorbikes`."""
    session = BrowseSession()

    _browse(session, manufacturer_ids=[])

    assert "manufacturer_id IN" not in _sql_at(session, 1)


@pytest.mark.parametrize("sort", sorted(BROWSE_ORDERINGS))
def test_every_sort_compiles_to_its_pinned_order_by(sort: Any) -> None:
    """Price sorts put NULLs last in both directions; `id` tiebreaks ascending."""
    session = BrowseSession()

    _browse(session, sort=sort)

    assert BROWSE_ORDERINGS[sort] in _sql_at(session, 1)


def test_the_page_projects_identity_plus_the_summary_columns_only() -> None:
    """A card is a teaser: no draft values, no uncompared long tail."""
    session = BrowseSession()

    _browse(session)
    sql = _sql_at(session, 1)

    assert (
        "SELECT motorbikes.id, motorbikes.query_name, motorbikes.manufacturer_id, "
        "motorbikes.buildingline, motorbikes.model_name, motorbikes.year_from, "
        "motorbikes.year_to, manufacturers.name AS manufacturer_name" in sql
    )
    for field in catalogue_search_service.SUMMARY_SPEC_FIELDS:
        assert f"motorbike_specs.{field}" in sql
    for field in set(catalogue_search_service.COMPARISON_SPEC_FIELDS) - set(
        catalogue_search_service.SUMMARY_SPEC_FIELDS
    ):
        assert f"motorbike_specs.{field}" not in sql


def test_a_browse_row_carries_every_summary_key_with_plain_values() -> None:
    """`Decimal` unwrapped, missing verified numbers explicitly `None`."""
    session = BrowseSession(
        total=1,
        rows=[_browse_row(category="naked", power_kw=Decimal("35.0"), msrp_eur=Decimal("6800.00"))],
    )

    rows, total = _browse(session)

    assert total == 1
    assert [row.motorbike_id for row in rows] == [BIKE_ID]
    assert rows[0].name == "Honda CB500F"
    assert rows[0].manufacturer_id == MANUFACTURER_ID
    assert set(rows[0].values) == set(catalogue_search_service.SUMMARY_SPEC_FIELDS)
    assert rows[0].values["power_kw"] == 35.0
    assert isinstance(rows[0].values["power_kw"], float)
    assert rows[0].values["msrp_eur"] == 6800.0
    assert rows[0].values["seat_height_mm"] is None
    # `parts` is loaded in the same statement — no extra round trip per row.
    assert rows[0].parts.motorbike_id == BIKE_ID
    assert rows[0].parts.query_name == "Honda CB500F"


def test_a_model_without_a_verified_revision_is_still_a_browse_row() -> None:
    """The outer join's whole point, seen from the mapping side."""
    session = BrowseSession(total=1, rows=[_browse_row(manufacturer_id=None)])

    rows, _ = _browse(session)

    assert rows[0].manufacturer_id is None
    assert all(value is None for value in rows[0].values.values())
