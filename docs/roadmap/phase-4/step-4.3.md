---
phase: 4
step: "4.3"
title: Catalogue browse & image service reads
summary: The service layer for customer catalogue browsing — browse_motorbikes (outer-join verified specs, reused SpecFilters clauses, name/price sort), newest_approved_images, and a statuses parameter on list_images. No endpoints yet.
effort: 2
dependencies: ["3.17"]
---

# Step 4.3 — Catalogue browse & image service reads

**Effort: 2** — three service reads over existing tables, no endpoints, no
migration, with the SQL conventions already landed (3.7/3.8/3.11).

Binding contract: `docs/roadmap/phase-4/shared-knowledge.md` (read fully —
especially *Service contracts* and the NULL-spec browse rule). Also read the
Landed decisions of 3.7, 3.8 and 3.11 in
`docs/roadmap/phase-3/shared-knowledge.md` before writing SQL. Agent:
**backend-dev**. Zero deviations from the spec — if a deviation seems
necessary, stop and report instead of improvising.

## Outline

- `catalogue_search_service.browse_motorbikes(session, *, filters:
  SpecFilters, manufacturer_ids=None, sort=BrowseSort.NAME, limit, offset)
  -> tuple[list[BrowseRow], int]` — one page statement + one count
  statement; `Motorbike.id/name/manufacturer_id` + the 8 summary spec
  columns; `OUTER JOIN motorbike_specs` with `kind='verified'` **in the ON
  clause**; `WHERE status='approved'` + optional `manufacturer_id IN` +
  the existing private `_clauses(filters)` reused verbatim (do **not**
  restate any bound). Ordering: `name`/`-name`, or `msrp_eur` with
  `nulls_last()` in both directions, tiebreak `name, id`.
- `BrowseRow` frozen dataclass `(motorbike_id, name, manufacturer_id,
  values: dict)`, `Decimal` unwrapped via the existing `_plain`;
  `BrowseSort` StrEnum in the service.
- `product_service.newest_approved_images(session, motorbike_ids) ->
  dict[str, MotorbikeImage]` — one `DISTINCT ON (motorbike_id)` statement,
  `status='approved'`, ordered `motorbike_id, created_at DESC, id DESC`.
  Do **not** refactor `present_recommendations`' per-bike loop.
- `product_service.list_images` gains `statuses: Sequence[ImageStatus] |
  None = None` (default `None` = behaviour unchanged; existing callers and
  tests untouched).
- Nothing commits; no config keys; no migration.

## Verification

- `make backend-test` (or `uv run pytest`) green: compiled-SQL tests with a
  local `RecordingSession` (the 3.7 convention) proving outer-join +
  `_clauses` reuse + NULLS-LAST orderings + `DISTINCT ON`; a drift guard
  asserting `BrowseRow.values` keys ⊂ `COMPARISON_SPEC_FIELDS`; existing
  suite untouched. Lint + format green.

## Risks / notes

- The browse outer-join is **deliberately different** from
  `find_motorbike_ids`' inner join (the advisor's candidate rule) — do not
  "unify" them; the browse rule is: unfiltered browsing includes models
  without a verified spec revision, any stated spec filter excludes them.
- Append cross-step decisions to `shared-knowledge.md` under
  `## Landed decisions` (`### Step 4.3`).
