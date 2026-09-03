---
phase: 6
step: "6.10"
title: Identity columns and their validators
summary: One migration adds motorbikes.buildingline, type_codes and variants; Pydantic validators pin the caps and drop-with-warning semantics for both JSONB shapes; normalise_buildingline / list_buildinglines land next to product_service. No writers, no API change, no prompt change.
effort: 3
dependencies: ["6.9"]
---

# Step 6.10 — Identity columns and their validators

**Effort: 3** — one additive migration plus two carefully-specified validation
modules with table-driven tests; nothing is wired to a writer yet, which keeps
the blast radius to the schema and the new code.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (hard rules —
migration 2 of 4; D1 pins the shapes and the drop-with-warning semantics) and
`docs/roadmap/model-naming-data-model.md` §2.1 (buildingline + drift guard),
§2.2 (columns), §2.4 (`type_codes` rules), §2.5 (`variants` rules), §4.1
(helper signatures). **No writers, no API, no prompt change** — writing is
6.12/6.15, the API is 6.20. Agent: **backend-dev**. Zero deviations — a
deviation is a stop-and-report.

**Environment:** stack up for the psql check. Alembic head at step start is
6.9's revision (see its `### Step 6.9` entry) — anything else is a
stop-and-report.

## Outline

- New migration, `down_revision` = 6.9's revision id:
  - `buildingline` `sa.String(64)`, nullable;
  - `type_codes` `postgresql.JSONB`, `nullable=False, server_default=sa.text("'[]'::jsonb")`;
  - `variants` same shape/default;
  - composite index `op.create_index("ix_motorbikes_manufacturer_id_buildingline", "motorbikes", ["manufacturer_id", "buildingline"])`.
  Downgrade drops the index and the three columns.
- `backend/app/db/models/motorbike.py`: `BUILDINGLINE_LENGTH = 64`;
  `buildingline: Mapped[str | None]`, `type_codes: Mapped[list[Any]]` and
  `variants: Mapped[list[dict[str, Any]]]` (JSONB, matching server defaults);
  the composite index in a new `__table_args__`; docstring notes per D1
  (type codes are retrieval metadata, never identity, never customer-visible;
  the row is the base trim, `variants` carries deltas only).
- **New** `backend/app/services/identity_validation.py` — the single place the
  caps live:
  - `TYPE_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-/ ]{1,31}$")`,
    `MAX_TYPE_CODES = 8`, `MAX_VARIANTS = 20`, `VARIANT_NAME_LENGTH = 64`,
    `VARIANT_DESCRIPTION_LENGTH = 400`,
    `VARIANT_SPEC_KEYS = tuple(f for f in SPEC_FIELDS if f not in ("source_hints", "extracted_at"))`
    (spec values plus `extra`; the two extraction-bookkeeping columns are not
    trim deltas — see Risks);
  - `class Variant(BaseModel)`: `slug`, `name`, `specs: dict[str, Any] = {}`,
    `description: str = ""` with the §2.5 caps; `slug` is always recomputed as
    `product_service.slugify(name)`, never trusted from input;
  - `normalize_type_codes(raw: Sequence[str]) -> tuple[list[str], list[str]]` —
    returns `(kept, warnings)`: trim, upper-case, deduplicate, validate against
    the pattern, cap at 8; every dropped entry produces one warning string,
    **never** an exception (the `_assign_manufacturer` precedent, D1);
  - `normalize_variants(raw: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]` —
    same contract: an entry failing the `Variant` model, a duplicate slug
    within the list, an unknown `specs` key (key dropped, entry kept) and
    entries beyond 20 each yield a warning; order of kept entries is preserved
    (order = display order).
- `backend/app/services/product_service.py` — per §4.1, next to the service:
  `async def normalise_buildingline(session, manufacturer_id: str, name: str | None) -> str | None`
  (trim, collapse inner whitespace, `None` for empty, reuse the stored casing
  of a case-insensitive match under that manufacturer) and
  `async def list_buildinglines(session, manufacturer_id: str) -> list[str]`
  (distinct non-NULL values, for the review form and 6.20). Reads only — no
  writes, no commits.
- Tests: **new** `backend/tests/services/test_identity_validation.py`
  (table-driven: casing/dedup/pattern/cap for codes; slug recompute, caps,
  spec-key whitelist, duplicate slug, overflow for variants — each dropped case
  asserting its warning); additions to
  `backend/tests/services/test_product_service.py` for both helpers using the
  stubbed-session pattern already in that file.

## Verification

- Migration round trip (`upgrade head` → `downgrade -1` → `upgrade head`) in
  the container, output pasted;
  `docker compose exec postgres psql -U app -d application -c '\d motorbikes'`
  shows the three columns, their defaults/NOT NULLs and
  `ix_motorbikes_manufacturer_id_buildingline`.
- `make backend-test` + `make lint` green — the 6.9 rename plus these additive
  columns must not move a single existing assertion. Do **not** re-run 6.9's
  curl captures: nothing reads the new columns yet, so the wire cannot change.

## Risks / notes

- `VARIANT_SPEC_KEYS`: data-model §2.5 says keys are "the frozen spec column
  names … plus `extra`" — `SPEC_FIELDS` literally also contains `source_hints`
  and `extracted_at` (per-extraction bookkeeping). This step excludes those
  two as trim-delta keys. **Interpretation, flagged for the architect** — if
  overruled, it is a one-line constant change.
- Later steps depend on the exact names here: 6.12 (`assign_identity` calls the
  normalisers and `normalise_buildingline`), 6.15 (extraction validates through
  this module and feeds warnings to `_Run._warn`), 6.20 (API + `list_buildinglines`).
  Do not rename anything after landing.
- Append (`### Step 6.10`) to `shared-knowledge.md`: the migration revision id
  (6.13 chains on it), the module path `app/services/identity_validation.py`
  and the `(kept, warnings)` return convention.
