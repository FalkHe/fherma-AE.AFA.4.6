"""Structured catalogue search: typed spec filters in, motorbike ids out.

This is the structured half of the advanced-RAG pair. `retrieval_service`
answers "what does the prose say?"; this service answers "which bikes can
actually satisfy the stated constraints?" — and it answers it from the
`verified` specification revision of `approved` catalogue entries only, because
those are the only numbers the project is willing to show a customer.

Three rules live here:

* **Verified specs of approved models, always.** A `draft` revision is an
  extraction an admin has not signed off, so filtering on it would let an
  unreviewed number decide a recommendation. Both conditions are `WHERE`
  clauses, never a post-filter.
* **A missing value never matches.** A filter is a claim ("the seat must be at
  most 800 mm"), and a bike whose verified seat height is `NULL` cannot support
  that claim. SQL's three-valued logic drops those rows, which is exactly the
  intent: the project shows verified specs or nothing, and it never guesses one
  to keep a bike in the list.
* **Ids only.** `find_motorbike_ids` decides nothing about the projection: the
  caller says what it needs about the winners, and `get_verified_specs` is that
  second, explicit step (the retrieval leg never asks for it).

Two more entry points serve the step-3.11 agent tools, and they keep the same
three rules:

* `resolve_name` — the shared name→bike resolution every tool needs (a customer
  writes "CB500F", not a ULID): **exact slug → type code → substring**
  (`docs/roadmap/model-naming-data-model.md` §4.3), approved entries only,
  `None` rather than an exception when nothing matches. The type-code leg
  matches a normalised code against `type_codes` (D5) and, as a retrieval hint
  only, against `suggestion->'type_codes'` (D6); several matches is an
  ambiguous code, so it falls through to the substring leg rather than
  guessing.
* `get_verified_specs` — display values for a set of ids: the frozen
  specification columns of the `verified` revision, every field present, `None`
  where the catalogue has no verified number. Nothing is ever inferred to fill a
  gap; the comparison table shows the gap instead. Each entry also carries
  `parts: naming_service.NameParts`, loaded in the same statement, so a caller
  can render the name in its own context (`docs/roadmap/stage-01/phase-6/shared-knowledge.md`
  D5); `name` itself stays a rendered convenience for a caller with no context.

`browse_motorbikes` (step 4.3) serves the customer catalogue and keeps two of
the three rules — verified specs, approved models, no post-filtering — but
deliberately breaks the third: it joins the specification **outer**, so a model
that has no verified revision at all is still browsable. Browsing is a list of
the catalogue, not a claim about numbers; the moment the customer states a spec
filter, the same NULL-never-matches logic drops those models again. The advisor's
candidate rule (`find_motorbike_ids`, inner join) is untouched by that — the two
are different questions and stay two statements.

The filter shape itself lives with the translation schema
(`app.llm.query_translation.SpecFilters`) — one definition for the model's
output and the SQL's input, so a renamed bound cannot go unnoticed.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import ColumnElement, Select, UnaryExpression, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_spec import MotorbikeSpec, SpecKind
from app.llm.query_translation import SpecFilters
from app.services import naming_service, product_service

# Which frozen specification columns a comparison shows, in table order, and
# which it deliberately leaves out. Together they are exactly `SPEC_FIELDS` —
# the drift guard in `tests/services/test_catalogue_search_service.py` asserts
# that, so a new column forces a decision here instead of quietly never being
# comparable (the same guard 3.8 put on the filterable set).
COMPARISON_SPEC_FIELDS: tuple[str, ...] = (
    "category",
    "engine_cc",
    "cylinders",
    "power_kw",
    "torque_nm",
    "wet_weight_kg",
    "seat_height_mm",
    "tank_capacity_l",
    "top_speed_kmh",
    "abs",
    "a2_eligible",
    "price_band",
    "msrp_eur",
)
# `extra` and `source_hints` are a free-form long tail and per-field extraction
# provenance — internal bookkeeping, not a row a customer compares two bikes on
# (and neither is a scalar a table cell could hold); `extracted_at` says when an
# extraction ran, which is a curation fact, not a specification.
UNCOMPARED_SPEC_FIELDS: tuple[str, ...] = ("extra", "source_hints", "extracted_at")

# Which of those a catalogue *card* shows — the summary projection of
# `browse_motorbikes`, in frozen column order. A subset of the comparable set by
# construction (the drift guard in the tests asserts it): a browse card is a
# teaser, the full comparison table belongs to the detail view.
SUMMARY_SPEC_FIELDS: tuple[str, ...] = (
    "category",
    "engine_cc",
    "power_kw",
    "wet_weight_kg",
    "seat_height_mm",
    "a2_eligible",
    "price_band",
    "msrp_eur",
)


class BrowseSort(StrEnum):
    """The orderings the customer catalogue offers, spelled as they go on the wire.

    Members are the wire values (`sort=-msrpEur`), so the route validates against
    this enum instead of restating the vocabulary.
    """

    NAME = "name"
    NAME_DESC = "-name"
    MSRP_EUR = "msrpEur"
    MSRP_EUR_DESC = "-msrpEur"


@dataclass(frozen=True, slots=True)
class BrowseRow:
    """One catalogue card: identity plus the summary specification values.

    `values` carries every `SUMMARY_SPEC_FIELDS` key (snake_case, as the columns
    are named), `None` where the model has no verified number — including the
    case where it has no verified revision at all, which browsing still shows.
    `Decimal` is unwrapped like everywhere else in this module.

    `parts` is the row's `naming_service.NameParts`, loaded in the same
    statement (no per-row query); `name` is `render_name(parts)` — a rendered
    convenience for a caller with no context (D5). A caller that has the whole
    page as its context (the customer browse list) renders from `parts`
    directly instead of using this field.
    """

    motorbike_id: str
    name: str
    manufacturer_id: str | None
    values: dict[str, Any]
    parts: naming_service.NameParts


@dataclass(frozen=True, slots=True)
class VerifiedSpecs:
    """One approved catalogue entry with its verified specification values.

    `values` carries **every** `COMPARISON_SPEC_FIELDS` key (snake_case, as the
    columns are named — camelCase aliasing is the tool's job), and a key whose
    verified value is missing is present with `None`. Values are plain
    JSON-serializable Python (`Decimal` unwrapped to `float`), because they end
    up in a tool result and then in a JSONB column.

    `parts` is the entry's `naming_service.NameParts`, loaded in the same
    statement (no per-row query); `name` is `render_name(parts)` — a rendered
    convenience for a caller with no context (D5). A caller that has several
    entries as its context (a comparison, a shortlist) renders from `parts`
    directly instead of using this field.
    """

    motorbike_id: str
    name: str
    values: dict[str, Any]
    parts: naming_service.NameParts


async def find_motorbike_ids(session: AsyncSession, filters: SpecFilters) -> list[str]:
    """Return the ids of approved motorbikes whose verified specs match `filters`.

    Args:
        session: Session the single statement runs on; nothing is written, so
            no transaction is committed here.
        filters: The translated constraints. An empty filter set is not an
            error — it matches every approved motorbike that has a verified
            specification, which is the whole candidate space.

    Returns:
        Motorbike ids ordered by name (then id, so equally named entries keep a
        stable order). Ordering is the database's; the caller may cut the list
        but never has to re-sort it.
    """
    result = await session.execute(_build_statement(filters))
    return list(result.scalars().all())


async def resolve_name(session: AsyncSession, name: str) -> Motorbike | None:
    """Resolve a written model name to an approved catalogue entry.

    Three steps, most precise first (`docs/roadmap/model-naming-data-model.md`
    §4.3):

    1. the **exact slug** derived from the name (`" Suzuki  GSR 600 "` →
       `suzuki-gsr-600`), which already absorbs case, spacing and punctuation;
    2. a **type code** — the trimmed, upper-cased input matched by JSONB
       containment against `Motorbike.type_codes` (D5) or, as a retrieval hint
       only (D6), against `suggestion->'type_codes'`. Exactly one approved row
       matching wins; several is an ambiguous code and none is a miss — both
       fall through rather than guessing;
    3. a **substring match** on `query_name` *or* `model_name` (`ILIKE '%…%'`),
       which catches the partial names a conversation uses ("CB500F" → "Honda
       CB500F") and the model name an admin never typed as the `query_name`.
       Ordered by the shorter of the two matching names, then `query_name`,
       then the id — the shortest is the closest to what was asked for, and the
       tiebreakers make the answer deterministic rather than dependent on the
       plan.

    Substring rather than trigram similarity on purpose: `pg_trgm` is not
    installed in this schema and only step 3.1 may carry a migration this phase.
    The three steps are the pinned resolution order either way, so adding the
    extension later changes step 3 alone.

    Args:
        session: Session the lookups run on; nothing is written or committed.
        name: The model name as it was written. Blank resolves to `None`.

    Returns:
        The approved entry, or `None` when the catalogue has nothing under that
        name (or has it, but not approved — an unreviewed entry is not something
        a customer may be shown). **Never raises for an unknown name**: callers
        turn `None` into the pinned `{"unknownBike": …}` tool result or skip it.
    """
    text = " ".join(name.split())
    if not text:
        return None

    slug = product_service.slugify(text)
    if slug:
        motorbike = await product_service.get_by_slug(session, slug)
        if motorbike is not None and motorbike.status is MotorbikeStatus.APPROVED:
            return motorbike

    code_result = await session.execute(_type_code_match_statement(text.upper()))
    code_matches = list(code_result.scalars().all())
    if len(code_matches) == 1:
        return code_matches[0]

    result = await session.execute(_name_match_statement(text))
    return result.scalars().first()


async def get_verified_specs(
    session: AsyncSession, motorbike_ids: Sequence[str]
) -> list[VerifiedSpecs]:
    """Return the verified specification values of approved entries, in the given order.

    One statement, one `LEFT OUTER JOIN`: an approved entry *without* a verified
    revision still comes back — with every value `None`, which is the honest
    answer a comparison column must be able to show. An id that is unknown or
    not approved is simply absent from the result, so the caller can tell the
    two apart by length or by id.

    Args:
        session: Session the statement runs on; nothing is written or committed.
        motorbike_ids: The ids to load, in the order the answer should keep
            (`find_motorbike_ids` already returns them name-ordered, and a
            comparison keeps the order the customer named the bikes in). Empty
            returns `[]` without a round trip.
    """
    if not motorbike_ids:
        return []

    result = await session.execute(_specs_statement(motorbike_ids))
    found = {row["id"]: row for row in result.mappings().all()}
    parts = {motorbike_id: _name_parts(row) for motorbike_id, row in found.items()}
    # Re-ordering in Python is alignment, not sorting: the caller's order is the
    # contract (comparison columns are aligned to it), and it cannot be
    # expressed as an `ORDER BY` over a set of ids.
    return [
        VerifiedSpecs(
            motorbike_id=motorbike_id,
            name=naming_service.render_name(parts[motorbike_id]),
            values={field: _plain(found[motorbike_id][field]) for field in COMPARISON_SPEC_FIELDS},
            parts=parts[motorbike_id],
        )
        for motorbike_id in motorbike_ids
        if motorbike_id in found
    ]


async def browse_motorbikes(
    session: AsyncSession,
    *,
    filters: SpecFilters,
    manufacturer_ids: Sequence[str] | None = None,
    sort: BrowseSort = BrowseSort.NAME,
    limit: int,
    offset: int,
) -> tuple[list[BrowseRow], int]:
    """Return one page of the customer catalogue plus the unpaginated total.

    Two statements, no third: the page and its count, both over the same
    conditions, so `meta.totalCount` can never disagree with what paging walks.

    The specification is joined **outer** with the `verified` condition in the
    `ON` clause: an approved model without a verified revision is part of
    unfiltered browsing (a card with empty spec lines is the honest answer),
    while any stated bound drops it again through three-valued logic — the
    pinned NULL-spec browse rule. The bounds themselves are `_clauses(filters)`
    verbatim, the same SQL the advisor's shortlist uses; this function adds no
    comparison of its own.

    Args:
        session: Session both statements run on; nothing is written or
            committed.
        filters: The stated spec bounds. An empty set narrows nothing.
        manufacturer_ids: `filter[manufacturer]` as manufacturer ULIDs; `None`
            or empty means unfiltered. An unknown id simply matches nothing.
        sort: One of the four pinned orderings; price sorts put NULLs last in
            both directions, so a model without a price never leads a page.
        limit: Page size, applied to the page statement only.
        offset: Rows to skip, applied to the page statement only.

    Returns:
        The page in the requested order, and the total number of models the
        conditions match.
    """
    conditions = _browse_conditions(filters, manufacturer_ids)

    total = await session.execute(_browse_count_statement(conditions))
    page = await session.execute(_browse_statement(conditions, sort, limit=limit, offset=offset))
    rows = []
    for row in page.mappings().all():
        parts = _name_parts(row)
        rows.append(
            BrowseRow(
                motorbike_id=row["id"],
                name=naming_service.render_name(parts),
                manufacturer_id=row["manufacturer_id"],
                values={field: _plain(row[field]) for field in SUMMARY_SPEC_FIELDS},
                parts=parts,
            )
        )
    return rows, total.scalar_one()


def _build_statement(filters: SpecFilters) -> Select[tuple[str]]:
    """Compose the one candidate-shortlist statement.

    Split out from `find_motorbike_ids` so the SQL can be read (and compiled in
    a test) without a database round trip.
    """
    return (
        select(Motorbike.id)
        # Inner join: a bike without a verified specification has nothing to
        # filter on and is therefore not a candidate, filters or no filters.
        .join(MotorbikeSpec, MotorbikeSpec.motorbike_id == Motorbike.id)
        .where(
            Motorbike.status == MotorbikeStatus.APPROVED,
            MotorbikeSpec.kind == SpecKind.VERIFIED,
            *_clauses(filters),
        )
        .order_by(Motorbike.query_name, Motorbike.id)
    )


def _clauses(filters: SpecFilters) -> list[ColumnElement[bool]]:
    """Return one SQL clause per stated bound, in `FILTER_FIELD_COLUMNS` order.

    Every field of `SpecFilters` is represented here; the test suite asserts
    that, so a new bound cannot be added to the schema and then quietly ignored
    by the search.
    """
    clauses: list[ColumnElement[bool]] = []
    if filters.categories:
        clauses.append(MotorbikeSpec.category.in_([item.value for item in filters.categories]))
    if filters.engine_cc_min is not None:
        clauses.append(MotorbikeSpec.engine_cc >= filters.engine_cc_min)
    if filters.engine_cc_max is not None:
        clauses.append(MotorbikeSpec.engine_cc <= filters.engine_cc_max)
    if filters.power_kw_min is not None:
        clauses.append(MotorbikeSpec.power_kw >= filters.power_kw_min)
    if filters.power_kw_max is not None:
        clauses.append(MotorbikeSpec.power_kw <= filters.power_kw_max)
    if filters.wet_weight_kg_max is not None:
        clauses.append(MotorbikeSpec.wet_weight_kg <= filters.wet_weight_kg_max)
    if filters.seat_height_mm_max is not None:
        clauses.append(MotorbikeSpec.seat_height_mm <= filters.seat_height_mm_max)
    if filters.a2_eligible is not None:
        # `IS true` / `IS false` rather than `=`: it reads as the three-valued
        # test it is, and an unknown eligibility never passes for either value.
        clauses.append(MotorbikeSpec.a2_eligible.is_(filters.a2_eligible))
    if filters.price_bands:
        clauses.append(MotorbikeSpec.price_band.in_([item.value for item in filters.price_bands]))
    return clauses


def _browse_conditions(
    filters: SpecFilters, manufacturer_ids: Sequence[str] | None
) -> list[ColumnElement[bool]]:
    """Return the `WHERE` of both browse statements, so they cannot drift apart.

    `approved` is the one non-negotiable condition (browsing is the customer
    surface); the manufacturer set and the stated bounds are optional, and the
    bounds are `_clauses` verbatim — no bound is restated here.
    """
    conditions: list[ColumnElement[bool]] = [Motorbike.status == MotorbikeStatus.APPROVED]
    if manufacturer_ids:
        conditions.append(Motorbike.manufacturer_id.in_(list(manufacturer_ids)))
    conditions.extend(_clauses(filters))
    return conditions


def _browse_join() -> ColumnElement[bool]:
    """Return the `ON` clause of the browse outer join.

    The `verified` condition sits here rather than in the `WHERE` for the same
    reason as in `_specs_statement`: on the outer side of the join a `WHERE`
    would drop every model that has no verified revision, which browsing is
    meant to keep.
    """
    return and_(
        MotorbikeSpec.motorbike_id == Motorbike.id,
        MotorbikeSpec.kind == SpecKind.VERIFIED,
    )


def _browse_statement(
    conditions: Sequence[ColumnElement[bool]], sort: BrowseSort, *, limit: int, offset: int
) -> Select[Any]:
    """Compose the one page statement `browse_motorbikes` issues.

    The `manufacturers` join is **outer**, like the specification join: a row
    without a `manufacturer_id` (or, defensively, a dangling one) still browses
    — it just sorts and renders as if it had no brand.
    """
    columns = [getattr(MotorbikeSpec, field) for field in SUMMARY_SPEC_FIELDS]
    return (
        select(
            Motorbike.id,
            Motorbike.query_name,
            Motorbike.manufacturer_id,
            Motorbike.buildingline,
            Motorbike.model_name,
            Motorbike.year_from,
            Motorbike.year_to,
            Manufacturer.name.label("manufacturer_name"),
            *columns,
        )
        .outerjoin(Manufacturer, Manufacturer.id == Motorbike.manufacturer_id)
        .outerjoin(MotorbikeSpec, _browse_join())
        .where(*conditions)
        .order_by(*_browse_order_by(sort))
        .limit(limit)
        .offset(offset)
    )


def _browse_count_statement(conditions: Sequence[ColumnElement[bool]]) -> Select[tuple[int]]:
    """Compose the matching count statement — same joins, same conditions.

    A plain `count()` is exact here: `motorbike_specs` holds at most one row per
    (motorbike, kind) and `manufacturer_id` is a to-one reference, so neither
    join can ever multiply a model into two rows. The `manufacturers` join is
    added here too even though nothing in the count needs it, so both browse
    statements share the exact same `FROM` shape.
    """
    return (
        select(func.count())
        .select_from(Motorbike)
        .outerjoin(Manufacturer, Manufacturer.id == Motorbike.manufacturer_id)
        .outerjoin(MotorbikeSpec, _browse_join())
        .where(*conditions)
    )


def _browse_order_by(sort: BrowseSort) -> tuple[UnaryExpression[Any], ...]:
    """Return the pinned `ORDER BY` of a browse page.

    `name`/`-name` can no longer sort on a display column — there is not one —
    so it is the composite an alphabetical catalogue actually wants: brand,
    then model, then (ascending only) the year range, id always the final,
    ascending tiebreak so paging stays stable. Price sorts put NULLs last in
    **both** directions — a model without a verified price is not the cheapest
    and not the most expensive, it is unknown, and it never leads a page.
    """
    if sort is BrowseSort.NAME:
        return (
            Manufacturer.name.asc().nulls_last(),
            Motorbike.model_name.asc().nulls_last(),
            Motorbike.year_from.asc().nulls_last(),
            Motorbike.id.asc(),
        )
    if sort is BrowseSort.NAME_DESC:
        return (
            Manufacturer.name.desc().nulls_last(),
            Motorbike.model_name.desc().nulls_last(),
            Motorbike.id.asc(),
        )
    if sort is BrowseSort.MSRP_EUR:
        return (
            MotorbikeSpec.msrp_eur.asc().nulls_last(),
            Motorbike.query_name.asc(),
            Motorbike.id.asc(),
        )
    return (
        MotorbikeSpec.msrp_eur.desc().nulls_last(),
        Motorbike.query_name.asc(),
        Motorbike.id.asc(),
    )


def _type_code_match_statement(code: str) -> Select[tuple[Motorbike]]:
    """Compose the type-code leg of `resolve_name` (step 2 of the three).

    JSONB containment (`@>`) against the typed `type_codes` column (D5) or, as
    a retrieval hint only (D6) — reading a claim to find a row, never
    surfacing it — against the unverified `suggestion->'type_codes'`. Approved
    rows only; the caller decides what 0, 1 or several matches mean.
    """
    return select(Motorbike).where(
        Motorbike.status == MotorbikeStatus.APPROVED,
        or_(
            Motorbike.type_codes.contains([code]),
            Motorbike.suggestion["type_codes"].contains([code]),
        ),
    )


def _name_match_statement(text: str) -> Select[tuple[Motorbike]]:
    """Compose the substring fallback of `resolve_name` (step 3 of the three).

    Matches `query_name` *or* `model_name` — a customer writes the model, an
    admin typed the whole phrase — ordered by the shorter of the two matching
    names (`NULL` `model_name` losing to any actual match via the `32767`
    fallback), then `query_name`, then `id`: the shortest is the closest to
    what was asked for, and the tiebreakers make the answer deterministic.
    """
    pattern = f"%{_escaped(text)}%"
    return (
        select(Motorbike)
        .where(
            Motorbike.status == MotorbikeStatus.APPROVED,
            or_(
                Motorbike.query_name.ilike(pattern, escape="\\"),
                Motorbike.model_name.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(
            func.least(
                func.char_length(Motorbike.query_name),
                func.coalesce(func.char_length(Motorbike.model_name), 32767),
            ),
            Motorbike.query_name,
            Motorbike.id,
        )
        .limit(1)
    )


def _escaped(text: str) -> str:
    """Neutralize the `LIKE` wildcards in text a customer wrote.

    `%` and `_` in a name would otherwise widen the pattern (a lone `%` matching
    every approved entry), which is a wrong answer, not a syntax error — so the
    input is escaped here rather than validated away.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _specs_statement(motorbike_ids: Sequence[str]) -> Select[Any]:
    """Compose the one display-values statement `get_verified_specs` issues.

    The `verified` condition sits in the `ON` clause, not in the `WHERE`: on the
    outer side of the join it would drop the very rows this projection is meant
    to keep (an approved entry whose specification was never verified). The
    `manufacturers` join is outer for the same defensive reason as the browse
    statement's — `manufacturer_id` may be `NULL`.
    """
    columns = [getattr(MotorbikeSpec, field) for field in COMPARISON_SPEC_FIELDS]
    return (
        select(
            Motorbike.id,
            Motorbike.query_name,
            Motorbike.buildingline,
            Motorbike.model_name,
            Motorbike.year_from,
            Motorbike.year_to,
            Manufacturer.name.label("manufacturer_name"),
            *columns,
        )
        .outerjoin(Manufacturer, Manufacturer.id == Motorbike.manufacturer_id)
        .outerjoin(
            MotorbikeSpec,
            and_(
                MotorbikeSpec.motorbike_id == Motorbike.id,
                MotorbikeSpec.kind == SpecKind.VERIFIED,
            ),
        )
        .where(
            Motorbike.id.in_(list(motorbike_ids)),
            Motorbike.status == MotorbikeStatus.APPROVED,
        )
    )


def _name_parts(row: Mapping[str, Any]) -> naming_service.NameParts:
    """Build `NameParts` from one row of `_specs_statement` or `_browse_statement`.

    Both statements project the identical set of naming columns (plus the
    manufacturer's display name, joined in as `manufacturer_name`), so one
    helper builds the parts for either caller — no per-row query either way.
    """
    return naming_service.NameParts(
        motorbike_id=row["id"],
        manufacturer=row["manufacturer_name"],
        buildingline=row["buildingline"],
        model_name=row["model_name"],
        year_from=row["year_from"],
        year_to=row["year_to"],
        query_name=row["query_name"],
    )


def _plain(value: Any) -> Any:
    """Return a specification value as plain JSON-serializable Python.

    Only `Decimal` needs unwrapping (`Numeric` columns): the value travels into a
    tool result and from there into a JSONB column, and `json.dumps` cannot
    encode a `Decimal`. `None` stays `None` — a missing verified number is never
    replaced by a zero or a guess.
    """
    return float(value) if isinstance(value, Decimal) else value
