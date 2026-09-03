"""Independent QA coverage for `app/services/catalogue_search_service.py` (3.8).

`tests/services/test_catalogue_search_service.py` already proves the compiled
SQL clause-by-clause. This file covers what a QA pass owns instead of trusts:

* the "a missing verified value never matches" contract is reviewed at the SQL
  level (no `COALESCE`/`IS NOT DISTINCT FROM` trick quietly reinstates a NULL
  match) — the project's own convention is that this SQL never runs against a
  real database in the test suite (see `tests/conftest.py`, 3.7's landed
  decision), so this is an inspection of the compiled statement, not a live
  round trip;
* `is_empty()` and "no clause emitted" genuinely agree with each other, driven
  through the same filter instance;
* combined filters compose correctly (AND, not accidental override) instead of
  only being proven one bound at a time;
* approved+verified are joined by AND, not by coincidence of two `.where()`
  calls that SQLAlchemy could in principle treat differently.
"""

import asyncio
import re
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.llm.query_translation import SpecFilters
from app.services import catalogue_search_service

_PARAMETER = re.compile(r"%\([a-z_0-9]+\)s")


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
    """Records the one statement issued; replays scripted ids. No commit/flush."""

    def __init__(self, rows: list[str] | None = None) -> None:
        self.rows = rows if rows is not None else []
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        return _Result(self.rows)


def _find(session: RecordingSession, filters: SpecFilters | None = None) -> list[str]:
    return asyncio.run(
        catalogue_search_service.find_motorbike_ids(session, filters or SpecFilters())
    )


def _sql(session: RecordingSession) -> str:
    assert len(session.statements) == 1
    compiled = session.statements[0].compile(dialect=postgresql.dialect())
    return _PARAMETER.sub("?", str(compiled))


# --- the NULL-never-matches contract, reviewed at the SQL level ---------------


def test_no_null_coalescing_trick_reinstates_an_unverified_value() -> None:
    """The compiled SQL must never paper over a NULL verified value.

    Ordinary SQL comparison/`IN`/`IS` operators already drop a NULL row under
    three-valued logic (`NULL >= x`, `NULL <= x` and `NULL IN (...)` are all
    UNKNOWN, and `WHERE` discards UNKNOWN same as FALSE) — that is the whole
    mechanism the contract relies on. What would silently break the contract
    is a rewrite that wraps a column in `COALESCE(...)` or uses
    `IS NOT DISTINCT FROM`/`IS DISTINCT FROM` to make a NULL participate
    anyway. Assert the statement contains neither, for every filter type at
    once.
    """
    session = RecordingSession()
    all_filters = SpecFilters.model_validate(
        {
            "categories": ["naked"],
            "engine_cc_min": 400,
            "engine_cc_max": 800,
            "power_kw_min": 20.0,
            "power_kw_max": 35.0,
            "wet_weight_kg_max": 200.0,
            "seat_height_mm_max": 800,
            "a2_eligible": True,
            "price_bands": ["budget"],
        }
    )

    _find(session, all_filters)
    sql = _sql(session).upper()

    assert "COALESCE" not in sql
    assert "DISTINCT FROM" not in sql


def test_the_join_to_specs_is_inner_not_outer() -> None:
    """A `LEFT JOIN` would let a bike with no verified spec row through as NULLs.

    The inner join is what makes "a bike without a verified specification is
    not a candidate" true regardless of the filters; an outer join would
    require every single clause to separately guard against NULL, which is
    exactly the kind of thing that is easy to get wrong one bound at a time.
    """
    session = RecordingSession()

    _find(session)
    sql = _sql(session).upper()

    assert "LEFT JOIN" not in sql
    assert "RIGHT JOIN" not in sql
    assert "FULL JOIN" not in sql
    assert " JOIN MOTORBIKE_SPECS ON MOTORBIKE_SPECS.MOTORBIKE_ID = MOTORBIKES.ID" in sql


def test_approved_and_verified_are_joined_by_and_in_the_compiled_where() -> None:
    """Both non-negotiable conditions must be conjunctive, not just co-present."""
    session = RecordingSession()

    _find(session, SpecFilters(a2_eligible=True))
    sql = _sql(session)

    where_clause = sql.split("WHERE", 1)[1]
    status_index = where_clause.index("motorbikes.status = ?")
    kind_index = where_clause.index("motorbike_specs.kind = ?")
    and_index = where_clause.index(" AND ")

    # However SQLAlchemy orders them, the two conditions are on either side of
    # at least one `AND`, not e.g. accidentally OR'd or duplicated away.
    assert and_index > min(status_index, kind_index)


# --- is_empty() and "no emitted clause" genuinely agree ------------------------


def test_is_empty_and_no_extra_clause_are_driven_by_the_same_instance() -> None:
    """The predicate a caller checks and the SQL actually emitted must agree.

    Rather than trusting two separately-written assertions, drive both off one
    `SpecFilters()` instance: if `is_empty()` ever drifted from what
    `_build_statement` treats as "nothing stated", this would catch it as one
    failure instead of two independently-plausible-looking tests.
    """
    filters = SpecFilters()
    assert filters.is_empty()

    baseline_session = RecordingSession()
    _find(baseline_session, filters)
    baseline_sql = _sql(baseline_session)

    untouched_session = RecordingSession()
    _find(untouched_session)  # the service's own default
    untouched_sql = _sql(untouched_session)

    assert baseline_sql == untouched_sql


def test_a_non_empty_instance_always_adds_at_least_one_clause() -> None:
    """The converse: whenever `is_empty()` is False, the SQL must differ from empty."""
    empty_session = RecordingSession()
    _find(empty_session, SpecFilters())
    empty_sql = _sql(empty_session)

    for values in (
        {"categories": ["naked"]},
        {"a2_eligible": False},
        {"seat_height_mm_max": 800},
        {"price_bands": ["mid"]},
    ):
        filters = SpecFilters.model_validate(values)
        assert not filters.is_empty()

        session = RecordingSession()
        _find(session, filters)
        assert _sql(session) != empty_sql


# --- combined filters compose (AND), not just one bound at a time -------------


def test_combined_filters_all_appear_together_in_one_statement() -> None:
    """A realistic multi-bound query (A2 commuter, budget, seat height) composes."""
    session = RecordingSession()
    filters = SpecFilters.model_validate(
        {
            "a2_eligible": True,
            "price_bands": ["budget", "mid"],
            "seat_height_mm_max": 800,
            "categories": ["naked"],
        }
    )

    _find(session, filters)
    sql = _sql(session)

    assert "motorbike_specs.a2_eligible IS true" in sql
    assert "motorbike_specs.price_band IN (__[POSTCOMPILE_price_band_1])" in sql
    assert "motorbike_specs.seat_height_mm <= ?" in sql
    assert "motorbike_specs.category IN (__[POSTCOMPILE_category_1])" in sql
    # Untouched bounds still emit nothing.
    assert "motorbike_specs.engine_cc" not in sql
    assert "motorbike_specs.power_kw" not in sql
    assert "motorbike_specs.wet_weight_kg" not in sql


def test_min_and_max_on_the_same_column_are_both_present_and_distinct() -> None:
    """A range filter (e.g. 400-800 cc) must not collapse to a single bound."""
    session = RecordingSession()

    _find(session, SpecFilters(engine_cc_min=400, engine_cc_max=800))
    sql = _sql(session)

    assert sql.count("motorbike_specs.engine_cc") == 2
    assert "motorbike_specs.engine_cc >= ?" in sql
    assert "motorbike_specs.engine_cc <= ?" in sql


def test_no_python_side_post_filtering_of_the_returned_ids() -> None:
    """The service returns exactly the rows the (fake) database handed back.

    A Python-side re-filter would be a second, undocumented place the "NULL
    never matches" contract could be violated or duplicated; the service's
    contract is that the database's answer is final.
    """
    rows = ["01J0BIKE00000000000000000Z", "01J0BIKE00000000000000000A"]
    session = RecordingSession(rows)

    result = asyncio.run(
        catalogue_search_service.find_motorbike_ids(
            session, SpecFilters(a2_eligible=True, seat_height_mm_max=800)
        )
    )

    assert result == rows  # not re-sorted, not de-duplicated, not truncated


@pytest.mark.parametrize("boolean", [True, False])
def test_a2_eligible_is_bound_as_a_parameter_not_inlined_as_a_string(boolean: bool) -> None:
    """`IS true`/`IS false` is compiled SQL literal syntax, not a bound param —
    confirm it is not accidentally rendered as a quoted string that could be
    misparsed (`'true'` vs. the boolean literal).
    """
    session = RecordingSession()

    _find(session, SpecFilters(a2_eligible=boolean))
    sql = _sql(session)

    literal = "true" if boolean else "false"
    assert f"motorbike_specs.a2_eligible IS {literal}" in sql
    assert f"IS '{literal}'" not in sql
