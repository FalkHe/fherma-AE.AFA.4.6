# Phase 4 — Shared Knowledge (binding contract)

This document is the **single source of truth** for every Phase-4 step. Every
agent working on a Phase-4 step must read it fully before writing code. When a
step file and this document disagree, this document wins. Do not deviate from
anything pinned here — if a deviation seems necessary, stop and report it
instead of improvising, because a parallel agent is building against the same
contract.

UI layout/state details live in [`ui-spec.md`](ui-spec.md) (binding for
frontend steps). Phase-1/2/2b/3 conventions
([`../phase-1/shared-knowledge.md`](../phase-1/shared-knowledge.md),
[`../phase-2/shared-knowledge.md`](../phase-2/shared-knowledge.md),
[`../phase-2b/shared-knowledge.md`](../phase-2b/shared-knowledge.md),
[`../phase-3/shared-knowledge.md`](../phase-3/shared-knowledge.md), each
including its Landed decisions) continue to apply — in particular the JSON:API
layer (`app/api/jsonapi.py`), route → service → SQLAlchemy layering with
services owning transactions, the compiled-SQL test convention
(`RecordingSession`, landed in 3.7), the image variant-URL formula
(`app/api/schemas/images.py`), and every frontend hook/stub/queryKeys
convention.

**Scope note (2026-08-28):** the former effort-8 step 4.2 was split into
steps 4.3–4.11 (this document + the step files). `step-4.2.md` remains as a
mapping marker only. Step 4.1 was superseded into Phase 3 earlier.

---

## Hard rules for every Phase-4 step

- **Zero migrations.** No Phase-4 step may add an Alembic revision (head
  stays `fb2747f937c4`). A schema need is a stop-and-report.
- **Zero new dependencies**, on either track. If a step believes it needs
  one, stop and report.
- **Zero new config keys.** `PAGE_SIZE = 24` (frontend) and `BrowseSort`
  are module constants.
- **No worker-relevant ORM changes** anywhere in this phase → no
  `docker compose restart app-worker` needed (the 2b.4 operational pin does
  not bite here).
- **Dispatch gate:** Phase-4 implementation steps start only after
  `phase-3-done` is tagged (3.15–3.17 finished). The recommendation-card
  link (4.9) builds on the card landed live in 3.15.

---

## Parallel-run rule

Two tracks run **concurrently**. Backend agents never touch `frontend/`;
frontend agents never touch `backend/`.

```text
backend-dev:  4.3 ─► 4.4 ─► ║S1║ ─► 4.5
frontend-dev: 4.6✓(ui-ux) ─► 4.7 ─► 4.8 ─► ║S1║ 4.9
docs-writer:                                     4.10
qa:                                              4.11 (after 4.5 + 4.9 + 4.10)
```

**Cross-track sync point (the only one):**

- **S1** — step 4.9 starts only after backend **4.4** is merged (it freezes
  the new OpenAPI surface). First action: regenerate API types via the
  landed image-independent sequence — `make generate-api`
  (`docker compose run --rm -T app-cli app openapi export >
  frontend/openapi.json`, then `node-cli pnpm exec openapi-typescript …`).

Frontend steps 4.7 and 4.8 need **zero backend code** (stub rule below).
Backend 4.5 (Q4 race fix) has no frontend counterpart, touches only chat
files, and may land any time after 4.4 in-track (or in a parallel backend
session — its files are disjoint from 4.3/4.4).

---

## Milestones (commit & tag points)

**Commit rule:** one commit per finished step (its verification green — lint,
types, tests). **Milestone rule:** a milestone is reached when all its steps
are merged on both tracks and its demo criterion passes; tag it
(`phase-4-m<N>`). Do not start a later milestone's sync step before the
earlier milestone's demo passes.

| Milestone | Steps (backend ∥ frontend) | Demo criterion (both tracks together) |
|---|---|---|
| **M1 — API & shells** | 4.3, 4.4 ∥ 4.6✓, 4.7, 4.8 | Plain-user curl proves the whole read contract (approved-only list, every filter narrows, both sorts, detail payload with specs/article/sources/images, 404 for non-approved ids, `GET /api/manufacturers` 200 as user, `/api/products` still 403); both pages complete on stub data with URL-persisted filters; **S1 open**. Tag `phase-4-m1`. |
| **M2 — Catalogue live** | 4.5 ∥ 4.9 | The product moment: browse → filter → shareable URL survives reload; a Phase-3 recommendation card clicks through to a real detail page with specs, prose, sources, image; concurrent double-POST on a chat answers exactly one 201 + one 409. Tag `phase-4-m2`. |
| **M3 — Acceptance** | 4.10 ∥ 4.11 | Demo script (incl. new catalogue chapter) green end-to-end; QA evidence filed. Tag `phase-4-done`. |

---

## Environment prerequisites

- **`phase-3-done` tagged** before dispatching any Phase-4 dev step —
  **satisfied** (tag verified 2026-08-28).
- **Demo-data note (N1 carry-over — resolved 2026-08-28):** all 3 approved
  models now carry an `msrp_eur` + `price_band` on both spec rows —
  **owner-approved guesses seeded for the demo, not researched prices**
  (BMW S 1000 XR 18 500 € premium · Honda CB500F 6 800 € mid · Suzuki
  GSR600 4 200 € budget). Price sort, `filter[priceBand]` and the price
  line are demoable. Real price research is deferred past Phase 4; 4.10
  must not describe these values as verified market data. See
  [`open-questions.md`](open-questions.md) (resolved OQ2).
- The compose stack must be up for 4.4/4.9/4.11 verifications (`make up`).

---

## Design decisions — final (recorded 2026-08-28)

- **D1 — customer visibility:** customer reads go through a **new read-only
  resource `catalogue-models`** — `/api/products` stays `current_admin` per
  the Phase-2 pin ("all Phase-2 endpoints are admin-only, reads included"),
  so no admin contract, test or hook moves, and customers can never see
  `draftSpec`. The Phase-3 pin "plain users cannot read `/api/products`"
  stays literally true; the persisted recommendation snapshots stay as
  pinned (self-contained, unchanged).
- **D2 — filters:** the route parses query params into the **3.8
  `SpecFilters`** (one definition of the filter vocabulary) and reuses
  `catalogue_search_service`'s clause builder — no duplicated SQL.
  Manufacturer filtering is **by manufacturer ULID**;
  **`GET /api/manufacturers` (+detail) relaxes `current_admin` →
  `current_user`** — exactly the decision Phase 2b reserved for Phase 4;
  wire shape unchanged, admin UI unaffected.
- **D3 — sort:** `name` (default) | `-name` | `msrpEur` | `-msrpEur`; price
  sorts **NULLS LAST in both directions** (a priceless bike never leads),
  tiebreak `name, id`.
- **D4 — detail payload:** one endpoint, everything embedded. Prose
  (`article`) = the **Wikipedia document's `content_markdown` only** —
  scraped product/magazine pages are *not* served wholesale to customers
  (marketing-biased, exactly what the project vision avoids); they appear in
  the `sources` list (title + external URL — the grading requirement
  satisfied outside the chat). `documents` and `product-images` get **no
  customer-facing endpoints**.
- **D5 — URL identity: ULID.** Route param is `:motorbikeId` (matches the
  Phase-3 reserved href contract; the id already rides along in
  `RecommendationCard`'s single `recommendation` prop as
  `recommendation.motorbikeId`; step 4.2's `:productId` spelling is
  superseded).
- **D6 — zero migrations** (see hard rules).
- **D7 — Q4** (Phase-3 concurrent-turn 409 race) is fixed in Phase 4 as its
  own tiny step **4.5** — migration-free `SELECT … FOR UPDATE` on the chat
  row in the `POST /api/chat-messages` path. **Owner confirmed 2026-08-28**
  (former OQ1): the race is rarely reachable, so the least-effort,
  migration-free lock is the chosen fix — 4.5 stays in the phase. On
  landing 4.5, remove Q4 from `../phase-3/open-questions.md`.

---

## New JSON:API resource `catalogue-models` — final

Read-only. Whole router `Depends(current_user)` (**not** `current_admin` —
this is the customer surface; admins are users too). No `csrf_protect`
(no writes). **Approved models only, always** — for every role. Files:
`backend/app/api/schemas/catalogue_models.py`,
`backend/app/api/endpoints/catalogue_models.py`, registered in
`backend/app/main.py` keeping the existing alphabetical router ordering
(the 2b.3 precedent).

### List — `GET /api/catalogue-models`

`CatalogueModelSummaryAttributes` (slim, scalars only, all camelCase):

| Attribute | Type | Source |
|---|---|---|
| `name` | string | `motorbikes.name` |
| `manufacturer` | string \| null | derived name via `manufacturer_service.get_by_ids` (the 2b pattern) |
| `category` | string \| null | verified spec |
| `engineCc` | number \| null | verified spec |
| `powerKw` | number \| null | verified spec |
| `wetWeightKg` | number \| null | verified spec |
| `seatHeightMm` | number \| null | verified spec |
| `a2Eligible` | boolean \| null | verified spec |
| `priceBand` | string \| null | verified spec |
| `msrpEur` | number \| null | verified spec |
| `imageUrl` | string \| null | card variant of the **newest approved** image (`variant_urls(...).card`); client derives thumb via the pinned `_card.webp` → `_thumb.webp` suffix swap and prefixes `VITE_API_URL` in dev (3.13/2.20 precedent) |

Deliberately absent: `slug`, `status`, `draftSpec`, `verifiedSpec`,
timestamps.

**Filters** (comma-separated members = OR within a family; families are
AND-ed):

| Wire name | Semantics |
|---|---|
| `filter[category]` | pinned `SpecCategory` vocabulary; unknown member → **400 `invalid-filter`** |
| `filter[priceBand]` | pinned `PriceBand` vocabulary; unknown member → **400 `invalid-filter`** |
| `filter[manufacturer]` | manufacturer ULIDs; an unknown id matches nothing (empty result, **not** an error) |
| `filter[engineCcMin]` / `filter[engineCcMax]` | typed numeric query params (junk → FastAPI default 422) |
| `filter[powerKwMin]` / `filter[powerKwMax]` | typed numeric |
| `filter[wetWeightKgMax]` | typed numeric |
| `filter[seatHeightMmMax]` | typed numeric |
| `filter[a2Eligible]` | typed `bool` |

**NULL-spec browse rule (pinned):** a verified-spec value that is NULL never
matches a stated filter on that column, and a model with **no verified
revision at all** is excluded by any stated spec filter but **included when
unfiltered** — outer-join semantics, deliberately different from
`find_motorbike_ids`' inner join, which stays the advisor's candidate rule
untouched.

**Sort:** `sort` = `Literal["name","-name","msrpEur","-msrpEur"]`, default
`name`; price NULLS LAST in both directions. **Exact ORDER BY (pinned for
4.3's compiled-SQL tests):** `name` → `name ASC, id ASC`; `-name` →
`name DESC, id ASC`; `msrpEur` → `msrp_eur ASC NULLS LAST, name ASC, id
ASC`; `-msrpEur` → `msrp_eur DESC NULLS LAST, name ASC, id ASC` — the `id`
tiebreak is always ASC. Junk → default FastAPI 422, no new error code.

**Pagination:** standard `page[number]`/`page[size]` (default/max 100),
`meta.totalCount`.

### Detail — `GET /api/catalogue-models/{motorbike_id}`

`CatalogueModelAttributes`:

- `name`, `manufacturer` (derived name | null) — deliberately **not**
  `modelName`/`yearFrom`/`yearTo`: the ui-spec renders neither, and
  unconsumed attributes are speculative surface (QA finding, 2026-08-28);
- `specs` — object with **exactly the 13 frozen camelCase fields**
  (`COMPARISON_SPEC_FIELDS` via `catalogue_search_service.
  get_verified_specs`; nulls explicit; **never** `extra`, `source_hints`,
  `extracted_at` — extraction provenance stays admin-only);
- `article` — string | null: the Wikipedia document's `content_markdown`
  (first document with `source_type == 'wikipedia'`), rendered client-side
  with react-markdown, **raw HTML off** (retrieved web content — this is the
  named domain security measure);
- `sources` — `[{sourceTitle, sourceUrl}]`, Wikipedia-first then
  `createdAt` (`document_service.list_for_motorbike` order verbatim) — no
  `sourceType` (the UI detects URL-less uploads by null `sourceUrl`); never
  `contentMarkdown`/`rawPath`;
- `images` — `[{thumb, card, detail, attribution}]`, **approved only**,
  newest first, via the pinned `variant_urls` formula (attribution shown —
  licence compliance).

Unknown / non-approved id → **404 `not-found`** (backlog / in_review /
rejected / unknown indistinguishable — no existence leak).

**Error codes:** reuse `not-found`, `invalid-filter`. **No new error codes
in Phase 4.**

### `manufacturers` auth change (4.4)

Router dependency in `backend/app/api/endpoints/manufacturers.py`:
`current_admin` → `current_user`. Wire shape, sorting, pagination unchanged.

**`useManufacturers()` pagination (pinned):** one request with
`page[size]=100`, **no page walk** — the table holds a handful of rows; if
`meta.totalCount` ever exceeds 100 that is a stop-and-report, not a reason
to add walking.

---

## Service contracts — final (4.3; routes never restate this SQL)

Route → service → SQLAlchemy; nothing here commits.

- **`catalogue_search_service.browse_motorbikes(session, *, filters:
  SpecFilters, manufacturer_ids: Sequence[str] | None = None, sort:
  BrowseSort = BrowseSort.NAME, limit: int, offset: int) ->
  tuple[list[BrowseRow], int]`** — one page statement + one count statement.
  `SELECT` of `Motorbike.id/name/manufacturer_id` + the 8 summary spec
  columns, `OUTER JOIN motorbike_specs` with `kind='verified'` **in the ON
  clause** (the 3.11 `get_verified_specs` precedent), `WHERE
  status='approved'` + optional `manufacturer_id IN` + the existing private
  `_clauses(filters)` **reused verbatim** (the 3.8 pin: one filter
  vocabulary, no duplicated SQL). `BrowseRow` is a frozen dataclass
  `(motorbike_id, name, manufacturer_id, values: dict)` with `Decimal`
  unwrapped via the existing `_plain`. `BrowseSort` is a StrEnum in the
  service. Ordering per D3.
- **`product_service.newest_approved_images(session, motorbike_ids) ->
  dict[str, MotorbikeImage]`** — one `DISTINCT ON (motorbike_id)` statement,
  `status='approved'`, ordered `motorbike_id, created_at DESC, id DESC`
  (the set-based version of 3.13's per-bike loop in
  `present_recommendations`; that tool is **not** refactored this phase).
- **`product_service.list_images`** gains optional `statuses:
  Sequence[ImageStatus] | None = None` (default `None` = behaviour
  unchanged) for the detail gallery.
- **Detail assembly lives in the endpoint** and composes existing reads
  only: `product_service.get_motorbike` (+ approved check),
  `catalogue_search_service.get_verified_specs`,
  `manufacturer_service.get_by_ids`, `document_service.list_for_motorbike`
  (article = first `wikipedia` document), `list_images(statuses=[APPROVED])`.

**Q4 fix contract (4.5):** `chat_service` gains a locking read (e.g.
`lock_owned_chat` or `get_owned_chat(..., for_update=True)`) used **only**
in the `POST /api/chat-messages` path, taking the chat row `WITH FOR
UPDATE` so `heal_stale_turn`'s check-then-act serializes per chat; the
second concurrent POST blocks, then sees the fresh `active_operation_id` →
409 `response-pending`. No wire change, no migration, `GET` paths untouched.

**Test conventions:** compiled-SQL assertions with a local
`RecordingSession` (the 3.7/3.8 convention — `FakeAsyncSession` cannot
interpret joins); a drift guard asserting `BrowseRow.values` keys ⊂
`COMPARISON_SPEC_FIELDS`.

---

## Frontend conventions — delta

File placement, stub pattern, envelope unwrapping, error-type conventions
and Material-Symbols icons carry over from Phases 1–3 unchanged. Full
layouts: [`ui-spec.md`](ui-spec.md).

**Routes** (in `frontend/src/App.tsx`, under `RequireAuth`):
`/catalogue` → `CatalogueRoute` (index), `/catalogue/:motorbikeId` →
`CatalogueModelRoute`.

**Files:**

| File | Content | Step |
|---|---|---|
| `frontend/src/routes/CatalogueRoute.tsx` | list page; owns the URL-param state | 4.7 |
| `frontend/src/routes/CatalogueModelRoute.tsx` | detail page | 4.8 |
| `frontend/src/components/CatalogueFilters.tsx` | filter panel bound to `useSearchParams` only — **no duplicate local state** | 4.7 |
| `frontend/src/components/CatalogueModelCard.tsx` | grid card: image `srcSet`/lazy, name, category, price chip, headline specs | 4.7 |
| `frontend/src/components/ModelSpecTable.tsx` | grouped 13-field verified-spec table (ui-spec §4.3) | 4.8 |
| `frontend/src/components/ModelImageGallery.tsx` | gallery with thumbnails + attribution (ui-spec §4.2) | 4.8 |
| `frontend/src/components/ModelSources.tsx` | out-of-chat provenance block, grading-critical (ui-spec §4.5) | 4.8 |
| `frontend/src/hooks/useCatalogueFilters.ts` | search-param parse/normalize/write helpers + `parseCatalogueFilters` (never a stub — pure URL logic) | 4.7 |
| `frontend/src/components/specFields.ts` | **extended** with `formatSpecEnum` (existing exports untouched) | 4.7 |

**Hook files (pinned — one file per replacement step so stubs die
wholesale):**

| File | Exports | Stubbed in | Made real in |
|---|---|---|---|
| `frontend/src/hooks/useCatalogueModels.ts` | `useCatalogueModels(filters)`, `useManufacturers()` + types `CatalogueListItem`, `Manufacturer` | 4.7 | 4.9 (deleted wholesale) |
| `frontend/src/hooks/useCatalogueModel.ts` | `useCatalogueModel(motorbikeId)` + types `CatalogueModelDetail`, `CatalogueImage`, `ModelSource`, `CatalogueError` (`status` + `code`, `ProductError` shape) | 4.8 | 4.9 (deleted wholesale) |

**Pinned UI-side rules:**

- **SPA URL search params are pinned in ui-spec §3.2** (`category`,
  `priceBand`, `manufacturer`, `ccMin/ccMax`, `kwMin/kwMax`, `seatMax`,
  `weightMax`, `a2`, `sort` `name|-name|price|-price`, `page`) — short,
  shareable, defaults omitted. **The data hook owns the one SPA→wire
  mapping** (spelled out in the ui-spec preamble; `price` ↔ `msrpEur`);
  renderers never see wire names. The TanStack Query key derives from the
  normalized parsed-params object.
- `PAGE_SIZE = 24` module constant, sent as `page[size]=24`;
  **server-driven pagination** (MUI `Pagination`) — deliberately *not* the
  admin walk-all-pages pattern, because `page` lives in the URL.
- UI filter set = **full wire parity**: manufacturer, category, priceBand,
  engineCc min/max, powerKw min/max, seatHeightMm max, wetWeightKg max,
  a2Eligible (reconciliation 2026-08-28 — the designer's panel, ui-spec
  §3.4).
- Detail spec table reuses `frontend/src/components/specFields.ts`
  (`SPEC_FIELD_KEYS`, `specFieldLabel/specFieldUnit/formatSpecValue`) — no
  second label table.
- `frontend/src/queryKeys.ts` gains `catalogue.{list(filters), detail(id)}`
  and `manufacturers.list()` — a **separate `["catalogue", …]` namespace**
  from the admin `["products", …]` keys (different shape/visibility;
  invalidation traffic must not churn across surfaces).
- `frontend/src/hooks/useServerEvents.ts` (in 4.9, not the stub steps):
  `product.updated` additionally invalidates `["catalogue"]`; reconnect
  blanket gains `["catalogue"]` + `["manufacturers"]`.
- i18n: new `catalogue.*` block + `nav.catalogue`; **R9 hoist (approved)**:
  `admin.review.specs.categoryValues`/`priceBandValues` move verbatim to
  `common.specEnums.category/priceBand`, the admin spec form is re-pointed
  (the one admin file 4.7 touches), and catalogue surfaces render enum
  values through `formatSpecEnum` with verbatim fallback. Chat surfaces
  keep rendering enum values verbatim (Phase-3 rule unchanged).
- **Recommendation-card link (4.9):** wrap the card content in
  `<CardActionArea component={RouterLink}
  to={`/catalogue/${recommendation.motorbikeId}`}>` — the formula reserved
  in the **Phase-3** ui-spec §9, spelled out in **Phase-4** ui-spec §6;
  **nothing else changes** in `RecommendationCard`. In particular its
  private `imageVariants()` helper stays private — the catalogue hooks
  implement their own `_card.webp` → `_thumb.webp` swap + `VITE_API_URL`
  prefix; this duplication is **deliberate** (rule of three — no shared
  module yet).

---

## Config keys / dependencies

**None.** No new config keys, no new dependencies, on either track (hard
rules above).

---

## Merge-friction files

Backend: `backend/app/main.py` (router registration, 4.4). Step 4.5 touches
only `backend/app/services/chat_service.py` +
`backend/app/api/endpoints/chat_messages.py` — disjoint from 4.3/4.4.

Frontend: `frontend/src/App.tsx` · `frontend/src/queryKeys.ts` ·
`frontend/src/hooks/useServerEvents.ts` ·
`frontend/src/locales/en/translation.json` ·
`frontend/src/components/AppLayout.tsx` (nav entry).

**Single-Alembic-head rule: no Phase-4 migration at all.**

---

## Landed decisions

Appended by implementing agents when a step finishes — decisions later steps
depend on. 1–3 bullets per step, no prose.

### Step 4.3 (catalogue browse & image service reads)

- **`catalogue_search_service` new public surface (4.4 consumes it verbatim):**
  `SUMMARY_SPEC_FIELDS` (the 8 card columns, frozen `SPEC_FIELDS` order —
  `category, engine_cc, power_kw, wet_weight_kg, seat_height_mm, a2_eligible,
  price_band, msrp_eur`), `BrowseSort` StrEnum whose **members are the wire
  values** (`NAME="name"`, `NAME_DESC="-name"`, `MSRP_EUR="msrpEur"`,
  `MSRP_EUR_DESC="-msrpEur"` — the route validates against the enum, it does not
  restate the vocabulary), frozen `BrowseRow(motorbike_id, name,
  manufacturer_id, values)` with snake_case `values` keys (camelCase aliasing is
  the schema's job) and `Decimal` unwrapped to `float`.
- **`browse_motorbikes` = count statement first, then the page** (both over
  `_browse_conditions(filters, manufacturer_ids)` = `status='approved'` +
  optional `manufacturer_id IN` + `_clauses(filters)` verbatim, both over the
  same outer join with `kind='verified'` in the `ON`). `manufacturer_ids=None`
  **and** `[]` both mean unfiltered (the `list_motorbikes` precedent); the plain
  `count(*)` is exact because `motorbike_specs` is unique per (motorbike, kind).
  Nothing commits; `find_motorbike_ids`' inner join is untouched.
- **`product_service`:** `newest_approved_images(session, motorbike_ids) ->
  dict[str, MotorbikeImage]` (one `DISTINCT ON`, empty ids → `{}` without a
  round trip, a model with no approved image is **absent** from the mapping —
  callers render the placeholder); `list_images(..., statuses=None)` where
  `None` **and** `[]` mean unfiltered, so the customer gallery must pass
  `statuses=[ImageStatus.APPROVED]` explicitly. Both statements are split into
  private `_…_statement` helpers so they compile in tests without a database.

### Step 4.4 (`/api/catalogue-models` + manufacturers read relax)

- **Wire (generated types 4.9 builds on):** components `CatalogueModelSummaryAttributes`
  (list) / `CatalogueModelAttributes` + `CatalogueModelSpecs` / `CatalogueSource` /
  `CatalogueImage` — `category` and `priceBand` are typed with the **existing**
  `SpecCategory`/`PriceBand` enum components (literal unions in TS, not bare
  `string`), `CatalogueImage` **extends `ImageVariants`** (`thumb`/`card`/`detail`
  + `attribution`), every `specs` field is required-and-nullable (an approved
  model with no verified revision answers 13 explicit nulls). `imageUrl` is the
  `card` variant, path-only (`/media/…`) — the client prefixes `VITE_API_URL`.
- **Route mechanics:** `sort` is typed as the **`BrowseSort` enum** (component
  `BrowseSort`, junk → FastAPI 422, default `name`); `filter[category]` /
  `filter[priceBand]` are parsed via `jsonapi.parse_filter` + the vocabulary enum
  → unknown member = 400 `invalid-filter`; `filter[manufacturer]` is passed
  through to `browse_motorbikes` unvalidated (unknown id → empty page, 200).
  Beware: `SpecFilters`' inherited quantity validators **silently drop a bound
  outside the field's plausibility range** (e.g. `filter[engineCcMin]=1` < 25 cm³
  ⇒ unstated), so an absurd bound widens rather than empties the result.
- **`manufacturers` router is now `current_user`** (anonymous still 401); the two
  Phase-2 "non-admin → 403" tests in `tests/api/test_manufacturers.py` were
  rewritten to assert the 200. Endpoint tests for the new resource live in
  `tests/api/test_catalogue_models.py` and monkeypatch only the two **join**
  reads (`browse_motorbikes`, `get_verified_specs`) — `FakeAsyncSession` cannot
  interpret joins; everything else runs against seeded rows.

### Step 4.5 — NOT landed (stopped for a decision, 2026-08-28)

- **Q4 stays open; no code changed** (backend tree untouched, suite 1181 green).
  Race reproduced live on `main`: 2 parallel `POST /api/chat-messages` → 2×201,
  2 `chat.response` operation rows (2 runs).
- **The outlined fix is provably insufficient:** `lock_owned_chat`
  (`SELECT … FOR UPDATE`) before `heal_stale_turn`, everything else unchanged,
  still gave 2×201 / 2 operations in 3/3 live runs — `append_user_message`
  **commits** (and `operation_service.create` commits again) *before*
  `active_operation_id` is ever written, so the row lock dies before the claim
  exists and the woken competitor still reads a NULL pointer.
- **Three Phase-3 pins are jointly unsatisfiable with a row lock:** (1) healing
  check strictly *before* `append_user_message`, (2) `start_response` strictly
  *after* it, (3) "every `chat_service` public function commits". Check and
  claim therefore sit in different transactions; **no lock can serialize a
  check-then-act split across a commit.** Fixing 4.5 requires relaxing (2) or
  (3) — plus a seam for `operation_service.create`'s internal commit — which is
  a pin change, i.e. a coordinator/owner decision, not a dev-agent one.

### Step 4.7 (catalogue list on stubs)

- **Hook contracts 4.9 must preserve verbatim** (`useCatalogueModels.ts` is
  deleted wholesale): `PAGE_SIZE = 24` is exported **from that file** (the
  route imports it to derive `pageCount`), `useCatalogueModels(filters:
  CatalogueFilters) -> UseQueryResult<CatalogueModelPage>` with
  `placeholderData: keepPreviousData`, `useManufacturers() ->
  UseQueryResult<Manufacturer[]>` (`staleTime` 5 min), types
  `CatalogueModelPage = {items, totalCount}`, `Manufacturer = {id, name}` and
  `CatalogueListItem = {motorbikeId, name, manufacturer, category, priceBand,
  engineCc, powerKw, wetWeightKg, seatHeightMm, image: {card, thumb} | null}`
  — **id field is `motorbikeId`, not `id`**, and the hook (not the card) owns
  the `_card.webp` → `_thumb.webp` swap + `VITE_API_URL` prefix. `msrpEur` /
  `a2Eligible` are deliberately absent from the row (nothing renders them;
  the server filters and sorts on them).
- **`useCatalogueFilters.ts` is the only URL logic** (survives 4.9): exports
  `parseCatalogueFilters`, `countActiveFilters`, `useCatalogueFilters()` →
  `{filters, setFilter, setPage, clearFilters, activeFilterCount}` plus the
  pinned vocabularies `SPEC_CATEGORY_VALUES` / `PRICE_BAND_VALUES` /
  `CATALOGUE_SORT_VALUES` and the types `CatalogueFilters` /
  `CatalogueSort` / `SpecCategory` / `PriceBand`. `setPage` is an **addition**
  to the ui-spec §3.3 return set (the page write must omit the default and use
  `replace: true` like every other write — duplicating that in the route would
  put URL logic outside this module); `setFilter` still always deletes `page`.
- **Landed conventions for 4.8/4.9:** `formatSpecEnum(t, "category" |
  "priceBand", value)` in `components/specFields.ts` over the hoisted
  `common.specEnums.*` (R9 done — `admin.review.specs.*Values` deleted,
  `ModelSpecsPanel` re-pointed); `queryKeys.catalogue.{all,list(filters),
  detail(id)}` + `queryKeys.manufacturers.{all,list()}`; **all** §9 i18n keys
  incl. the unused `catalogue.detail.*` block are already merged (4.8 adds no
  strings); `renderWithProviders(ui, {initialEntries})` now seeds the
  `MemoryRouter` (how a URL-driven screen is mounted in tests); route table
  has `catalogue` as a nested route whose only child is the index — 4.8 adds
  the `:motorbikeId` child. Card/route DOM notes: card links are found by
  `a[href^="/catalogue/"]`, not by accessible name (name resolution over 24
  cards costs seconds).

### Step 4.8 (model detail on stubs)

- **Hook contract 4.9 must preserve verbatim** (`useCatalogueModel.ts` is deleted
  wholesale): `useCatalogueModel(motorbikeId) ->
  UseQueryResult<CatalogueModelDetail>` (`enabled: motorbikeId !== ""`, **no
  `retry` override** — a 404 surfaces after the default backoff, the admin-review
  precedent), `class CatalogueError extends Error {status, code}` (the
  `ProductError` shape; the route branches on `status === 404` only), and the
  types `CatalogueModelDetail {motorbikeId, name, manufacturer, specs, article,
  sources, images}` / `CatalogueImage {thumb, card, detail, attribution}` (wire
  variant keys) / `ModelSource {sourceTitle, sourceUrl}`. **`specs` is an inline
  13-field object on `CatalogueModelDetail`** — components take
  `CatalogueModelDetail["specs"]`, so no extra type is exported or imported.
- **Stub fixtures (ids are the 4.7 `stubId()` spelling, so the grid links land):**
  `01STUBSUZUKIGSR60000000000` fully populated (13/13 specs, 2 images, GFM +
  `<script>` article, 3 sources incl. a duplicate URL and a URL-less upload),
  `01STUBHONDAREBEL5000000000` sparse (0 images, `article: null`, "Licence &
  safety" all-null, 1 source), `01STUBMISSING0000000000000` — and **every other
  id 404s**, which is also how the unapproved case is demoed.
- **Landed component conventions:** `ModelSpecTable` owns the
  `catalogue.detail.specsHeading` heading **and** the private group→field
  mapping (`msrpEur` via `Intl.NumberFormat(i18n.language, EUR)`, enums via
  `formatSpecEnum`, everything else `formatSpecValue` + `specFieldUnit`);
  `ModelImageGallery`/`ModelSpecTable`/`ModelSources` export **only** their
  component (the `react-refresh/only-export-components` lint rule forbids
  co-exported constants — the pinned gallery height `{xs:240, md:400}` is
  therefore spelled in both the gallery and the route skeleton, as ui-spec
  §4.2/§4.6 spell it); the article's react-markdown config lives in
  `CatalogueModelRoute` with raw HTML off and markdown headings demoted to
  `h3`/`h4` (deliberately not shared with `MessageBubble`'s — rule of three).
  Detail-page tests mount `<Routes><Route path="/catalogue/:motorbikeId" …>` via
  `renderWithProviders(..., {initialEntries})`; the 404 test wraps the route in a
  nested `QueryClientProvider` with `retry: false` (the `ConsultationChatRoute`
  precedent) to skip the ~7 s backoff.

### Step 4.9 (catalogue wired live + recommendation-card link)

- **Both stub hooks are gone; the pinned exports are unchanged**, so no renderer
  moved. `useCatalogueModels.ts` owns the whole SPA→wire mapping (`toListQuery`:
  absent filters **omitted**, `a2` sent only when on, `WIRE_SORT` `price ↔
  msrpEur`, `page[size]=24`) and derives the thumb from the card-only `imageUrl`
  by suffix swap; `useCatalogueModel.ts` only prefixes `VITE_API_URL` onto the
  three variants the detail payload already carries. Types come from the
  generated schema (`CatalogueListItem` = `Pick<CatalogueModelSummaryAttributes,
  …> & {motorbikeId, image}`, `CatalogueModelDetail` = `{motorbikeId} &
  CatalogueModelAttributes`). **`catalogueError(status, body)` is exported from
  `useCatalogueModel.ts` and used by both hooks** (the `useChatMessages` →
  `useChats` precedent) — every catalogue failure is a `CatalogueError`.
  `useManufacturers` is one request with `page[size]=100`, no walk (dev DB: 3).
- **Test fixtures moved out of the dying stubs into
  `frontend/src/test/catalogueApi.ts`** — a `stubFetch(catalogueApi)` handler
  that serves `/api/catalogue-models`, `…/{id}` (404 for anything else) and
  `/api/manufacturers` in the **wire** vocabulary. The two catalogue route test
  files gained only the import plus a `beforeEach`; every on-screen assertion is
  the one written on stubs. Reuse this handler for any later catalogue screen
  test instead of mocking the hooks.
- **SSE + card:** `product.updated` → `["products"]`, `["catalogue"]`; the
  reconnect blanket is products, operations, chats, chatMessages, catalogue,
  manufacturers (`useServerEvents.test.ts` asserts the exact call order — append
  new prefixes at the end). `RecommendationCard` is now a
  `CardActionArea component={RouterLink}` over unchanged content; its Phase-3
  "offers no dead controls" test became "links its whole surface…".
- **Open defect (not fixed here — outside the step's files):**
  `frontend/src/routes/LoginRoute.tsx:59` reads only `from.pathname`, so the
  login redirect **drops the search string**: a shared *filtered* catalogue URL
  lands a fresh session on a bare `/catalogue`. Path-only deep links (detail
  pages) are unaffected. Fix is one line (carry `pathname + search`); needs a
  coordinator decision.

### Step 4.10 (demo-script catalogue chapter)

- **The Phase-3 demo walkthrough had no companion doc** — 3.16 landed only
  `backend/scripts/demo_conversation.py`'s own module docstring (a scripted,
  self-cleaning API demo with no browser-replayable artefact left behind).
  4.10 creates that companion doc at **`docs/demo-walkthrough.md`** (linked
  from `README.md` "Further reading") rather than editing the script's
  docstring, per this step's "documentation only, no code changes" scope.
  Later steps that extend the demo (Phase 5.3 mentioned in 3.16's docstring)
  should extend this file, not invent a second one.
- **The LoginRoute search-string defect flagged above (step 4.9) is fixed as
  of `HEAD aa1f108`** ("Preserve query string in post-login redirect") —
  live-verified during 4.10: a filtered `/catalogue?...` URL now survives the
  login redirect. The walkthrough documents this as working; no further
  action needed from a later step.

### Step 4.11 fixes (mobile overflow defects)

- **AppBar nav is icon-only below `sm`** (`AppLayout.tsx`): each destination
  renders through a local `NavButton` (`to`/`icon`/`label`) that shows a
  Material Symbols glyph at `xs` (`forum` / `two_wheeler` /
  `admin_panel_settings`) and the text label from `sm` up, with `aria-label`
  always carrying the label — a nav entry stays one real `RouterLink` and
  keeps its accessible name at every width. Only `minWidth` is overridden
  (`{ xs: 0, sm: 64 }`); padding stays MUI-default so `sm`-and-up widths are
  byte-for-byte the old ones (137/104/64px). The 4.7 title-hiding tweak alone
  left 377px of toolbar content at 360px; measured 3 nav glyphs + toggle +
  account now fit with headroom (admin included). Add future nav entries via
  `NavButton`, not a bare `Button`.
- **Retrieved-article tables scroll inside a wrapper**
  (`CatalogueModelRoute.tsx`): the react-markdown `components` map gains
  `table: ProseTable`, a `Box` with `maxWidth: "100%"` + `overflowX: "auto"`
  around the `<table>`. Any future markdown surface rendering GFM tables at
  full page width needs the same override — the `MARKDOWN_SX` styling alone
  does not bound a Wikipedia-width table. Chat's `MessageBubble` has no such
  wrapper (it relies on the bubble's own `maxWidth: "100%"`) and was
  deliberately left untouched — this fix was scoped to the two reported
  defects.
