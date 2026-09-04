# Phase 2b — Shared knowledge (binding contract)

Interlude phase between Phase 2 (catalogue & ingestion, done) and Phase 3
(advisor, sliced but not started). **Goal: manufacturers become a first-class
table instead of a free-text column on `motorbikes`, extraction fills it, and
an admin-only read API exposes it.** Admin UI for managing manufacturers is
**out of scope** (owner decision, 2026-08-27).

Everything in this file is pinned. Phase-2 conventions apply verbatim unless
superseded here: ULID `String(26)` PKs via `ULIDPrimaryKeyMixin`,
`TIMESTAMPTZ` UTC with server defaults, naming convention on `Base.metadata`,
**no ORM relationships** (FK + service-level lookup, the `get_specs` pattern),
services own transactions and commit, JSON:API conventions from
[`../phase-2/shared-knowledge.md`](../phase-2/shared-knowledge.md).

---

## Owner decisions (2026-08-27)

- **Logo storage**: MEDIA_DIR-relative path (`logo_path`), mirroring
  `motorbike_images.original_path` and the existing `/media` static serving.
  No external URLs, no upload machinery yet — the column stays NULL until an
  admin surface exists.
- **Legacy column**: `motorbikes.manufacturer` (String(64) NULL) is
  **dropped** in the 2b.1 migration, after backfill. One source of truth; the
  API wire shape is preserved by derivation.
- **Extraction**: extended now (2b.2) — otherwise nothing ever writes the
  table, since admin UI is out of scope.
- **Read API**: `GET /api/manufacturers` (+ detail) added now (2b.3),
  admin-only like every Phase-2 endpoint. Customer-facing exposure (catalogue
  filter) stays a Phase-4 step-4.2 decision.
- **Backfill of existing bikes**: via a deterministic CLI command, **never**
  re-ingestion — re-ingestion's fresh-run semantics delete documents and
  embeddings, which would break Phase-3 prerequisite A2 (approved, embedded
  models must survive).
- **Not** in the products payload: manufacturer `description`/`logoPath`. The
  pinned `products` attribute set stays frozen.

## DB schema — final (step 2b.1, the only Phase-2b migration)

**`manufacturers`**

| Column | Type / constraint |
|---|---|
| `id` | `String(26)` PK (ULID) |
| `name` | `String(64) NOT NULL` — display form, first-seen casing ("Suzuki") |
| `slug` | `String(64) NOT NULL`, unique `uq_manufacturers_slug` — same pinned slugify as motorbikes (lowercase, `[^a-z0-9]+` → `-`, trimmed); the get-or-create identity, so "BMW " / "bmw" dedupe |
| `description` | `Text NULL` — short description; NULL until an admin surface exists |
| `logo_path` | `String(512) NULL` — MEDIA_DIR-relative (see owner decisions) |
| `created_at`, `updated_at` | as `motorbikes` (server default `now()`, server-side `onupdate` — the refresh-after-write rule applies) |

**`motorbikes` changes**

- Add `manufacturer_id String(26) NULL`, FK → `manufacturers.id` (default NO
  ACTION — no delete path exists), index `ix_motorbikes_manufacturer_id`.
- **Drop** `manufacturer String(64)`.

**Migration** — one revision off head `0a65339a924a`. Upgrade order:
create `manufacturers` → add FK column + index → backfill (`SELECT DISTINCT`
trimmed, non-empty legacy strings → one manufacturers row each, ULIDs
generated in the migration via `from ulid import ULID`; slugify inlined as
the pinned two-line regex, never imported from `app.services`) → drop the
legacy column. Downgrade reverses exactly: re-add `manufacturer String(64)
NULL`, restore names from the related rows, drop index/FK/column, drop table.
Round-trip is lossless up to whitespace/casing normalization. No enum types →
no `DROP TYPE`. (On the live dev DB the backfill is a no-op: all existing
rows have `manufacturer = NULL` — verified 2026-08-27.)

## Services

`backend/app/services/manufacturer_service.py` (module-level functions,
`AsyncSession` first, public functions commit):

- `normalize_name(raw) -> str | None` — strip, collapse internal whitespace,
  truncate to 64; empty → `None`.
- `get_or_create(session, name) -> Manufacturer` — identity is the slug; on
  `IntegrityError` (parallel ingestions) rollback + re-select.
- `get_by_ids(session, ids) -> dict[str, Manufacturer]` — read companion for
  the products routes (the `get_specs` pattern).
- `list_manufacturers(session, *, limit, offset) -> (rows, total)` — ordered
  by `name`, for the 2b.3 endpoint.

`product_service.assign_manufacturer(session, motorbike, manufacturer_id:
str | None)` — sets the FK, commits, `_announce`s `product.updated` (the
backlog renders the name live).

## JSON:API resources

**`products` — wire shape unchanged.** The pinned attribute set stays
verbatim; `manufacturer` is now **derived**: the related manufacturer's
`name`, `null` when unassigned. No relationships/includes (the jsonapi layer
still defers include machinery). `_resource(...)` gains a
`manufacturers: Mapping[str, Manufacturer]` argument filled by one
`get_by_ids` call per request. Expected consequence: `make generate-api`
leaves `frontend/src/api/schema.d.ts`'s products types byte-identical.

**`manufacturers`** (step 2b.3) — resource type `manufacturers`, attributes
`name, slug, description, logoPath, createdAt, updatedAt` (camelCase, `null`
when absent). Read-only:

- `GET /api/manufacturers` — page-number pagination, sorted by `name`; no
  filters.
- `GET /api/manufacturers/{id}` — 404 code `not-found` like products.
- Whole router `Depends(current_admin)` (Phase-2 rule: reads included, this
  is an admin surface). No writes — creation happens only via
  `get_or_create` (extraction/CLI).

## Extraction (step 2b.2)

- `ExtractedSpec` gains `manufacturer: str | None` (brand name only, e.g.
  "Suzuki"; null if unclear). **Excluded from `to_spec_values()`** — it is
  not in the frozen `SPEC_FIELDS` and `upsert_draft_spec` would raise. The
  overridden `model_json_schema` lists every property in `required`, so the
  new field rides along (the 2.17 OpenRouter constraint).
- Prompt (`spec_extraction.md`): one added instruction — brand only, no model
  suffix; untrusted-content hygiene unchanged.
- `spec_extraction_service`: after the successful `upsert_draft_spec`,
  `normalize_name` → `get_or_create` → `assign_manufacturer`. Null/empty →
  skip. **A bad manufacturer never costs the run its spec** (same policy as
  the rest of the service).

## CLI (step 2b.2)

`app catalogue set-manufacturer <slug> "<name>"` — deterministic, no LLM:
resolve motorbike by slug (unknown → stderr + exit 1, the `fetch-image`
precedent), `get_or_create` + `assign_manufacturer`. This is the backfill
tool for the 3 existing approved bikes and the only manual correction path
until an admin UI exists.

## Invariants QA must protect (2b.4)

- Embeddings intact: `SELECT count(*) FROM chunks WHERE embedding IS NOT
  NULL` unchanged across the whole phase (Phase-3 prerequisite A2).
- Products API wire shape unchanged; status transition matrix undisturbed.
- Migration downgrade/upgrade round-trip with a pre-seeded legacy string.

## Step order

`2b.1` → (`2b.2`, `2b.3` — independent, sequential dispatch) → `2b.4`
(acceptance; tag `phase-2b-done`). Phase 3 dispatching may then begin against
the updated head pointer.

## Landed decisions

Dev agents: append cross-step decisions here (one `### Step 2b.N` subsection
each), exactly like Phase 2. **2b.1 must record the new migration revision id
here** — phase-3's `shared-knowledge.md` and `step-3.1.md` reference it.

### Step 2b.1 (manufacturers table, migration & derived attribute)

- **Migration `485b2042d7f8` (`add_manufacturers_table`) is the new head**
  (revises `0a65339a924a`); the phase-3 head pointers in
  `../phase-3/shared-knowledge.md` and `../phase-3/step-3.1.md` now name it.
  Hand-written, not autogenerated (order: create table → FK column + index →
  backfill → drop legacy column); `alembic check` is clean, so the ORM fully
  expresses the schema. Round-trip verified on the dev DB with two
  differently-spelled legacy strings ("  Suzuki  " / "suzuki") — they backfilled
  into **one** row (grouping is on the slug, not the raw string) and the
  downgrade restored both as the normalised `Suzuki`.
- **`manufacturer_service` contract** (module-level, `AsyncSession` first,
  public functions commit): `normalize_name(raw: str | None) -> str | None`
  (strip, collapse internal whitespace, truncate 64, empty → `None`; casing
  kept), `get_or_create(session, name)` — **normalises `name` itself**, so a
  caller may pass raw text; it raises `ValueError` when the name has no slug
  characters (`"???"`), which 2b.2's extraction/CLI must treat as "skip the
  manufacturer, keep the spec"; `get_by_ids(session, ids) -> dict[str,
  Manufacturer]` (empty ids → `{}`, unknown id absent) and
  `list_manufacturers(session, *, limit, offset)` ordered by `name` **without a
  tiebreaker** (equal names derive the same unique slug, so a duplicate name
  cannot exist). `slugify` is imported from `product_service` — one rule for
  both tables; only the migration inlines it.
- **`product_service.assign_manufacturer(session, motorbike, manufacturer_id |
  None)`** commits and announces `product.updated`; `None` clears the reference.
  It is the only writer of `motorbikes.manufacturer_id`. On the API side
  `manufacturer` is derived in `endpoints/products.py`: `_resource(motorbike,
  specs, manufacturers)` plus `_manufacturers_of(session, motorbikes)` (one
  `get_by_ids` per request, list and detail), and a dangling/unknown id renders
  `null` rather than failing. `make generate-api` left
  `frontend/src/api/schema.d.ts` and `frontend/openapi.json` byte-identical.
- **Test seam for 2b.2/2b.4:** the shared `FakeAsyncSession` was left untouched
  (it still has no `rollback`); `tests/services/test_manufacturer_service.py`
  carries a local `_RacingSession` subclass that fails the first commit with
  `IntegrityError` and simulates the winning transaction's row, and
  `tests/api/test_products.py::_assign_manufacturer` is the fixture helper that
  creates the `manufacturers` row a derived attribute needs.

### Step 2b.2 (extraction fills the manufacturer, backfill CLI)

- **`extraction.NON_SPEC_FIELDS = ("manufacturer",)`** is the new name for "in the
  LLM schema, not in the frozen spec column set". `ExtractedSpec.manufacturer` is
  `str | None` with `BeforeValidator(_to_text)` (trimmed text, anything non-text →
  `None`; no truncation — `normalize_name` owns that), and `to_spec_values()` /
  `filled_fields()` still iterate `SPEC_FIELDS` only, so the exclusion is by
  construction. The overridden `model_json_schema` puts it in `required`
  automatically; **verified live** through OpenRouter (`app ingest extract-specs
  suzuki-gsr600`, 2026-08-27) — the 15-property schema is accepted and the model
  answers the brand. A later field of this kind only needs to be added to
  `NON_SPEC_FIELDS` and written by its own service call.
- **`spec_extraction_service._assign_manufacturer(session, motorbike, name)`** runs
  *after* `upsert_draft_spec` (never before — a bad brand must not cost the spec):
  `normalize_name` → `None` means skip silently; otherwise `get_or_create` +
  `product_service.assign_manufacturer` inside one broad `except Exception` that
  logs a warning and returns. No `rollback` is issued there — `get_or_create`
  already rolls back its own failed insert, and everything before it was committed
  — so the caller's session stays usable. `ExtractionResult` is unchanged: the
  brand is not reported in the outcome, only in the log.
- **`app catalogue set-manufacturer <slug> "<name>"`** (`backend/app/cli/catalogue.py`,
  registered in `main.py` before `chunks`): resolves the bike first (unknown slug →
  stderr + exit 1), then `get_or_create` (its `ValueError` for `"???"` → stderr +
  exit 1, nothing written) then `assign_manufacturer`; stdout is
  `"<slug> now belongs to manufacturer '<name>' (<id>)."`. `app catalogue` is now
  the home for deterministic, LLM-free catalogue corrections. **Live state left in
  place (2026-08-27):** `suzuki-gsr600`→Suzuki, `honda-cb500f`→Honda,
  `bmw-s-1000-xr`→BMW, 3 `manufacturers` rows, `description`/`logo_path` NULL;
  8 documents / 49 chunks / 49 embeddings unchanged by all of it.
- **Deliberate omissions for 2b.4:** the prompt rules were renumbered (brand is
  rule 6 of 13), no test asserts rule numbers; `tests/cli/test_catalogue.py`
  copies the `_SessionContextManager` + `_patch_sessionmaker` pattern from
  `tests/cli/test_users.py` rather than sharing it; the live re-extraction moved
  the Suzuki's **draft** `seat_height_mm` 800 → 785 (model variance) — the
  `verified` row and therefore the API payload are untouched.

### Step 2b.3 (`/api/manufacturers` read endpoints)

- **The resource is live as pinned.** `app/api/schemas/manufacturers.py`
  (`MANUFACTURER_TYPE = "manufacturers"`, `ManufacturerAttributes` with
  `ConfigDict(from_attributes=True)` and no request model at all — the
  `SpecAttributes` precedent) plus `app/api/endpoints/manufacturers.py`
  (`GET ""`, `GET "/{manufacturer_id}"`, router-level `Depends(current_admin)`,
  no `csrf_protect` because there is nothing to protect). Generated client
  operation ids: `list_manufacturers_api_manufacturers_get` and
  `get_manufacturer_api_manufacturers__manufacturer_id__get`; the
  `schema.d.ts` diff was purely additive (three hunks, zero deletions, products
  types byte-identical). Registered in `main.py` between `images` and
  `operations` (routers stay alphabetical).
- **No new service function for the detail route.** `_get_or_404` reuses
  `manufacturer_service.get_by_ids(session, [id]).get(id)`, so the 2b.1 service
  contract is unchanged and this module owns no query of its own. A later step
  that needs a real `get_manufacturer(session, id)` should add it to the service,
  not query here.
- **`app/api/endpoints/__init__.py` and `app/api/schemas/__init__.py` were left
  untouched**: both are docstring-only packages with no re-export registry
  (`main.py` imports the modules directly), so "register there" was a no-op —
  adding `__all__` lists would have been a new convention.
- **Live dev DB state unchanged** (2b.4 can rely on it): 3 manufacturers, 3
  assigned bikes, 8 source documents, 49 chunks, 49 embeddings, head
  `485b2042d7f8`. The smoke test used a throw-away account `tmp2b3admin`
  (registered via `/auth/register`, promoted, then set back to `user` — same
  precedent as `tmp2b2admin`); no admin session of it is left signed in.

### Step 2b.4 (acceptance run — QA finding)

- **PASS on all 7 criteria** (2026-08-27); tagged `phase-2b-done`.
- **Operational pin: `app-worker` does not hot-reload.** `app-web` runs
  `uvicorn --reload`, but the taskiq worker keeps the ORM it started with —
  after landing any step that changes `backend/app/db/models/` (or anything
  the worker imports), restart it: `docker compose restart app-worker`.
  During acceptance a stale worker crashed a queued ingestion with
  `UndefinedColumn: motorbikes.manufacturer` until restarted. Applies to
  every future phase (Phase 3's chat-response job runs in this worker).
- The criterion-1 downgrade→upgrade round-trip regenerates manufacturer ids
  (backfill creates fresh ULIDs) — assignments survive by name/slug, ids are
  not stable across a round-trip.
