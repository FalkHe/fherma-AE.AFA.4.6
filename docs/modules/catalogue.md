# Catalogue

Two audiences over one set of tables: admins curate through `/api/products`,
customers read through `/api/catalogue-models`. Identity and naming are
[`model-naming.md`](model-naming.md); how rows get their content is
[`ingestion.md`](ingestion.md).

## Tables

| Table | Shape |
|---|---|
| `motorbikes` | identity block + `status` + `suggestion` — see [`model-naming.md`](model-naming.md) |
| `motorbike_specs` | one row per `(motorbike_id, kind)`, `kind ∈ {draft, verified}`; every spec column nullable; `extra JSONB`, `source_hints JSONB`, `extracted_at` |
| `source_documents` | `source_type ∈ {wikipedia, product, technical, magazine, upload, listing}`, `source_url`, `source_title`, `raw_path`, `content_markdown`, `fetched_at` |
| `chunks` | `source_document_id` + denormalised `motorbike_id`, `sequence`, `text`, `heading_path`, `embedding vector(1536)`, `embedding_model`, generated `text_tsv` |
| `motorbike_images` | `source_url`, `attribution`, `status ∈ {pending, approved, rejected}`, `original_path` |
| `manufacturers` | `name`, `slug` UNIQUE, `description`, `logo_path` (both NULL — no admin surface) |
| `motorbike_used_prices` | see [`used-prices.md`](used-prices.md) |

**The 13 customer-visible spec fields** are frozen: `engineCc`, `cylinders`,
`powerKw`, `torqueNm`, `wetWeightKg`, `seatHeightMm`, `tankCapacityL`,
`topSpeedKmh`, `abs`, `a2Eligible`, `category`, `priceBand`, `msrpEur`. The
backend list (`SPEC_FIELDS`) additionally holds `extra`, `source_hints` and
`extracted_at`; the frontend's `SPEC_FIELD_KEYS` mirrors the 13 exactly, and
`spec_comparison` uses the same set.

Vocabularies: `category ∈ {naked, sport, sport_touring, touring, adventure,
cruiser, classic, scrambler, enduro, supermoto, scooter}`;
`price_band ∈ {budget (<5k€), mid (5–10k), upper (10–15k), premium (>15k)}`.
Units are fixed: mm, kg, kW, Nm, cm³, litres, km/h, EUR.

`a2_eligible` is derived on write **only** when the incoming value is null and
both inputs are known (`power_kw ≤ 35 AND power_kw/wet_weight_kg ≤ 0.2`); an
explicit value always wins, and the derivation re-runs on approval. Its known
data-quality gap is in [`../general/security.md`](../general/security.md#known-gaps).

## Status and transitions

```text
backlog   → ingesting
ingesting → in_review | backlog          (job failure)
in_review → approved | rejected
rejected  → ingesting                    (fresh ingestion)
approved  → (none)
```

Anything else is 422 `invalid-transition`. Status only ever changes through
`product_service.transition` — never by assignment.

**Approval is one transaction**: the draft spec is promoted to `verified` and
every pending image becomes `approved`. It additionally requires a complete
identity (422 `incomplete-identity`). No API path writes a `verified` row
directly.

**`rejected` is not terminal and deletes nothing** — the row, draft, documents
and images are retained, and a re-ingestion is one transition away.

Image transitions: `pending → approved|rejected`, `approved → rejected`,
`rejected → (none)`.

## Admin API

All admin-only, reads included; writes need CSRF.

| Endpoint | Notes |
|---|---|
| `GET /api/products?filter[status]=` | comma-separated statuses |
| `GET /api/products/{id}` | |
| `POST /api/products` | body carries `name` only → 201, already in status **`ingesting`**; duplicate slug → 409 `duplicate-model` |
| `PATCH /api/products/{id}` | attributes `identity`, `draftSpec`, `status` — applied in that order in one request |
| `GET /api/documents?filter[product]=` | filter required; unpaginated; `listing` rows deliberately shown |
| `GET /api/product-images?filter[product]=` | unpaginated |
| `PATCH /api/product-images/{id}` | status only |
| `GET /api/operations` | filters `entityType`, `entityId`, `status` |
| `GET /api/manufacturers/{id}/buildinglines` | |

`draftSpec` is a **full-object upsert**: an omitted field becomes NULL,
`extra` becomes `{}`, and a key outside `SPEC_FIELDS` is rejected. `rawPath`
and `originalPath` are never exposed. Image variant URLs are derived
(`{thumb,card,detail}`), never stored.

## Customer API

`current_user`, read-only, no CSRF. **Only approved models**; anything else is
404 — never 403.

`GET /api/catalogue-models`

| Filter | Notes |
|---|---|
| `filter[category]`, `filter[priceBand]` | comma-separated = OR; an unknown member is 400 `invalid-filter` |
| `filter[manufacturer]` | one ULID; an unknown id is an empty 200 |
| `filter[engineCcMin/Max]`, `filter[powerKwMin/Max]`, `filter[wetWeightKgMax]`, `filter[seatHeightMmMax]` | bounded by the extraction plausibility windows → 422 outside |
| `filter[a2Eligible]` | boolean |

Filter families are AND-ed. **A NULL spec value never matches a filter**, so a
model with no verified revision is excluded by any spec filter but included
when unfiltered (outer join).

`sort ∈ {name, -name, msrpEur, -msrpEur}`, default `name`; price sorts put NULL
last in both directions; tiebreak `name, id`. Pagination `page[number]` ≤ 10 000,
`page[size]` ≤ 100.

List attributes: `name`, `manufacturer`, `category`, `engineCc`, `powerKw`,
`wetWeightKg`, `seatHeightMm`, `a2Eligible`, `priceBand`, `msrpEur`, `imageUrl`
(card variant of the newest approved image, a `/media/…` path). No slug, no
status, no draft spec, no timestamps.

`GET /api/catalogue-models/{motorbikeId}` adds `specs` (all 13, nulls
explicit), `variants`, `article` (the Wikipedia document's Markdown, else
null), `sources[{sourceTitle, sourceUrl}]` (Wikipedia first) and
`images[{thumb, card, detail, attribution}]` (approved only, newest first).
`listing` documents are excluded from customer sources. There is no customer
endpoint for documents or images, and `typeCodes` is never exposed.

`GET /api/manufacturers` and `/{id}` are `current_user` — the catalogue needs
the filter vocabulary.

## Frontend

**Admin.** `/admin` is the backlog table (model / status / progress / updated /
actions), status filter in `?status=`, an add-model dialog, per-row "Start
ingestion", "Retry ingestion" (when the latest operation failed) and "Review".
`/admin/models/:motorbikeId` is the review screen with tabs in `?tab=`
(`identity`, `documents`, `specs`, `image`; default `documents`) and the
selected document in `?doc=`. Approve/Reject go through a confirm dialog, and
the approve dialog warns about unsaved edits. The Specs tab edits 8 of the 13
fields (`engineCc`, `powerKw`, `torqueNm`, `wetWeightKg`, `seatHeightMm`,
`a2Eligible` tri-state, `priceBand`, `category`); the rest survive through the
merge in `useSaveDraftSpec`. The Image tab is **reject-only** — approving the
model approves its pending image server-side, so no approve-image mutation
exists.

**Customer.** `/catalogue` holds all filter state in the URL: `category`,
`priceBand`, `manufacturer`, `ccMin`, `ccMax`, `kwMin`, `kwMax`, `seatMax`,
`weightMax`, `a2=1`, `sort` (`name|-name|price|-price`), `page`. Defaults are
omitted from the URL, writes use `replace: true`, and any filter or sort change
drops `page`. `PAGE_SIZE = 24`; the hook maps the short URL names and
`price ↔ msrpEur` onto the wire names in one place. Desktop shows a filter
sidebar, mobile a drawer with an active-filter badge.

`/catalogue/:motorbikeId` renders the name and manufacturer, variant chips,
the image gallery, a grouped spec table (engine / chassis / safety / market,
plus a trims group; a null renders no row), the used-price block *if* the
payload carries one, the "About" article through `UntrustedMarkdown` with
headings demoted and tables wrapped for scroll, and an always-expanded sources
list. A 404 renders an `EmptyState`.

`LiveConnectionAlert` is deliberately **not** shown on catalogue screens.
`product.updated` invalidates both `["products"]` and `["catalogue"]`;
`["productImages"]` is invalidated by the reject mutation only — no SSE event or
reconnect covers it.
