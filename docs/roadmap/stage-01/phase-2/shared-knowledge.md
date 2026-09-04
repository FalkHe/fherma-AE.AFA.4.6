# Phase 2 — Shared Knowledge (binding contract)

This document is the **single source of truth** for every Phase-2 step. Every
agent working on a Phase-2 step must read it fully before writing code. When a
step file and this document disagree, this document wins. Do not deviate from
anything pinned here — if a deviation seems necessary, stop and report it
instead of improvising, because a parallel agent is building against the same
contract.

UI layout/state details live in [`ui-spec.md`](ui-spec.md) (binding for
frontend steps). Phase-1 conventions
([`../phase-1/shared-knowledge.md`](../phase-1/shared-knowledge.md), including
its Landed decisions) continue to apply.

---

## Parallel-run rule

Two tracks run **concurrently**. Backend agents never touch `frontend/`;
frontend agents never touch `backend/`.

```text
backend-dev:  2.1 ─► 2.3 ─► 2.5 ─► 2.6 ─► 2.7 ─► 2.9 ─► 2.10 ─► 2.11 ─► 2.12
              ─► 2.14 ─► 2.16 ─► 2.17 ─► 2.18 ─► 2.19

frontend-dev: 2.2✓ ─► 2.4 ─► 2.8 ─► ║S1║ 2.15 ─► 2.13 ─► ║S2║ 2.20

qa:           2.21 (after 2.19 + 2.20)
```

**Cross-track sync points (the only two):**

- **S1** — step 2.15 starts only after backend **2.7** is merged (2.7 implies
  2.3 + 2.6 are in the OpenAPI schema). First action: `pnpm generate:api`
  (requires `app-web` up).
- **S2** — step 2.20 starts only after backend **2.17 and 2.9** are merged
  (2.17 implies 2.14; 2.9 provides the documents/images endpoints 2.20 wires).
  First action: regenerate types again.

Frontend runs 2.15 before 2.13 when S1 is already open (the default with the
milestone schedule below) — the dependency graph allows either order.

Frontend steps 2.2/2.4/2.8/2.13 need **zero backend code** (stub rules below).

**Within-track parallelism (optional second backend session):** 2.5,
2.10→2.11, and 2.16 are independent of the 2.1→2.3→2.6→2.7→2.9 mainline. Only
merge-friction files: `backend/pyproject.toml`/`uv.lock`, `compose.yaml`,
`backend/app/core/config.py`, `backend/app/cli/main.py`. **Never parallelize
two migration-bearing steps — 2.1, 2.6, 2.18 must land in that order (single
Alembic head).**

---

## Milestones (commit & tag points)

**Commit rule:** one commit per finished step (its verification green — lint,
types, tests). **Milestone rule:** a milestone is reached when all its steps
are merged on both tracks and its demo criterion passes; tag it
(`phase-2-m<N>`). Milestones are the points where frontend and backend
converge into something demoable — do not start a later milestone's sync step
before the earlier milestone's demo passes.

| Milestone | Steps (backend ∥ frontend) | Demo criterion (both tracks together) |
|---|---|---|
| **M1 — Plumbing & shells** | 2.1, 2.3, 2.5, 2.6, 2.7 ∥ 2.2✓, 2.4, 2.8 | Products API works via curl (create/filter/transition incl. 422s); `app operations demo` streams over `curl -N /api/events`; backlog UI renders stub rows with all states; S1 is open. |
| **M2 — Live backlog** | — ∥ 2.15 | First real FE+BE convergence: add a model in the UI → row persists without reload; `app operations demo` drives the progress cell live over SSE; filter/retry work against the real API. |
| **M3 — Real ingestion** | 2.9, 2.10, 2.11, 2.12, 2.14, 2.16, 2.17 ∥ 2.13 | `app ingest run "Suzuki GSR 600"` (worker up) → documents + image + draft spec, **live progress visible in the browser backlog**, row flips to `in_review`; review screen renders complete on stub data; S2 is open. |
| **M4 — Review live & knowledge base** | 2.18, 2.19 ∥ 2.20 | Full review flow in the browser against the really-ingested model: documents render, spec edit + save, image reject, approve → verified specs; chunks embedded with recorded model/dimensions. |
| **M5 — Phase acceptance** | 2.21 | The roadmap done-criterion end-to-end with evidence; tag `phase-2-done`. |

Backend continues 2.10/2.11/2.16 in parallel while frontend lands M2 — the
milestone gates only its own steps plus the demo.

---

## DB schema — final

ULID string PKs via the existing `ULIDPrimaryKeyMixin`; all timestamps
`TIMESTAMPTZ`, UTC; constraint/index names from the existing naming convention
on `Base.metadata`; native PG enums use `values_callable` so lowercase values
are stored (Phase-1 landed decision). ORM models define **no relationships**.

**`motorbikes`** (step 2.1)

| Column | Type / constraint |
|---|---|
| `id` | `String(26)` PK |
| `name` | `String(160) NOT NULL` — display name as entered ("Suzuki GSR 600") |
| `slug` | `String(160) NOT NULL`, unique `uq_motorbikes_slug` — service-side slugify: lowercase, `[^a-z0-9]+` → `-`, trimmed; no slugify dependency |
| `manufacturer` | `String(64) NULL` (filled by extraction/admin) — **superseded (Phase 2b, 2026-08-27)**: column dropped, replaced by `manufacturer_id` FK → `manufacturers`; see [`../phase-2b/shared-knowledge.md`](../phase-2b/shared-knowledge.md) |
| `model_name` | `String(128) NULL` |
| `year_from`, `year_to` | `SmallInteger NULL` |
| `status` | native enum `motorbike_status('backlog','ingesting','in_review','approved','rejected') NOT NULL`, server default `'backlog'`, index `ix_motorbikes_status` |
| `created_at`, `updated_at` | as `users` |

**Legal transition matrix** — enforced in `product_service.transition`;
anything else → 422 error code `invalid-transition`:

```text
backlog   → ingesting    (admin add auto-starts [from 2.14]; retry/start)
ingesting → in_review    (job success)
ingesting → backlog      (job failure — automatic)
in_review → approved     (side effects, ONE transaction: draft spec upserted
                          to verified; all pending images → approved)
in_review → rejected
rejected  → ingesting    (re-queue = fresh ingestion)
```

**`rejected` semantics (pinned): not terminal.** Row, draft spec, documents
and images are retained; the model is excluded from everything customer-facing
(Phase 3 filters `status = 'approved'` only); an admin re-queues via PATCH
status → `ingesting`. Approval **only ever** promotes the draft — no API path
writes `verified` rows directly.

**`source_documents`** (step 2.1)

| Column | Type / constraint |
|---|---|
| `id` | PK |
| `motorbike_id` | `String(26) NOT NULL` FK → motorbikes ON DELETE CASCADE, `ix_source_documents_motorbike_id` |
| `source_type` | native enum `source_type('wikipedia','product','technical','magazine','upload') NOT NULL` |
| `source_url` | `String(2048) NULL` (uploads have none) |
| `source_title` | `String(512) NOT NULL` |
| `raw_path` | `String(512) NOT NULL` — relative to `DATA_DIR` |
| `content_markdown` | `Text NOT NULL` |
| `fetched_at` | `TIMESTAMPTZ NOT NULL` |
| `created_at` | server default `now()` |

**`motorbike_specs`** (step 2.1) — one row per (motorbike, kind); `kind`
native enum `spec_kind('draft','verified')`; unique
`uq_motorbike_specs_motorbike_id_kind`.

**Core spec column set — FROZEN. Phase-3 tools filter on exactly these**
(API camelCase in parentheses):

| Column | Type | Unit / values |
|---|---|---|
| `category` | `String(32) NULL` | pinned vocabulary: `naked, sport, sport_touring, touring, adventure, cruiser, classic, scrambler, enduro, supermoto, scooter` |
| `engine_cc` (`engineCc`) | `Integer NULL` | cm³ |
| `cylinders` | `SmallInteger NULL` | count |
| `power_kw` (`powerKw`) | `Numeric(5,1) NULL` | kW |
| `torque_nm` (`torqueNm`) | `Numeric(5,1) NULL` | Nm |
| `wet_weight_kg` (`wetWeightKg`) | `Numeric(5,1) NULL` | kg (wet/kerb preferred; prompt normalizes) |
| `seat_height_mm` (`seatHeightMm`) | `SmallInteger NULL` | mm |
| `tank_capacity_l` (`tankCapacityL`) | `Numeric(4,1) NULL` | litres |
| `top_speed_kmh` (`topSpeedKmh`) | `SmallInteger NULL` | km/h |
| `abs` | `Boolean NULL` | |
| `a2_eligible` (`a2Eligible`) | `Boolean NULL` | derived on write **only when the incoming value is null** and both inputs are known: `power_kw <= 35 AND power_kw / wet_weight_kg <= 0.2`; an explicit (admin-set) value always wins |
| `price_band` (`priceBand`) | `String(16) NULL` | `budget` (<5 k€), `mid` (5–10 k€), `upper` (10–15 k€), `premium` (>15 k€) |
| `msrp_eur` (`msrpEur`) | `Integer NULL` | EUR |
| `extra` | `JSONB NOT NULL DEFAULT '{}'` | long tail; never filtered on |
| `source_hints` | `JSONB NULL` | per-field LLM provenance notes |
| `extracted_at` | `TIMESTAMPTZ NULL` | |

**Unit conventions project-wide: mm, kg, kW, Nm, cm³, litres, km/h, EUR.**
Phase-3 steps reuse these verbatim.

**`motorbike_images`** (step 2.1)

| Column | Type / constraint |
|---|---|
| `id` | PK |
| `motorbike_id` | FK CASCADE, `ix_motorbike_images_motorbike_id` |
| `source_url` | `String(2048) NOT NULL` |
| `attribution` | `Text NULL` (licence/author, from Wikipedia) |
| `status` | native enum `image_status('pending','approved','rejected') NOT NULL` default `'pending'` |
| `original_path` | `String(512) NOT NULL` — relative to `MEDIA_DIR` |
| `created_at` | |

Variant paths are **deterministic, never stored**:
`MEDIA_DIR/motorbikes/{motorbike_id}/{image_id}_{variant}.webp`. Ingestion
creates **at most one image row per run**; the UI renders the newest.

**`operations`** (step 2.6)

| Column | Type / constraint |
|---|---|
| `id` | PK |
| `type` | `String(64) NOT NULL` — `'ingestion'`, `'embeddings.rebuild'`, `'demo'` |
| `status` | native enum `operation_status('queued','running','succeeded','failed') NOT NULL` default `'queued'` |
| `progress` | `SmallInteger NOT NULL DEFAULT 0` (0–100) |
| `message` | `String(512) NULL` — current human-readable step (English, rendered verbatim in the admin UI, exempt from i18n) |
| `error` | `String(2048) NULL` |
| `entity_type`, `entity_id` | `String(32) NULL` / `String(26) NULL`, composite index `ix_operations_entity_type_entity_id` |
| `created_at`, `started_at NULL`, `finished_at NULL`, `updated_at` | |

**`chunks`** (step 2.18; pgvector extension already enabled in the baseline
migration)

| Column | Type / constraint |
|---|---|
| `id` | PK |
| `source_document_id` | FK CASCADE, `ix_chunks_source_document_id`; unique `uq_chunks_source_document_id_sequence` with `sequence` |
| `motorbike_id` | `String(26) NOT NULL` denormalized, `ix_chunks_motorbike_id` |
| `sequence` | `Integer NOT NULL` |
| `text` | `Text NOT NULL` |
| `heading_path` | `String(512) NULL` (`"Suzuki GSR600 > Design"`) |
| `page_number` | `SmallInteger NULL` (PDF-only; NULL in Phase 2) |
| `embedding` | `vector(1536) NULL` — nullable: 2.18 writes chunks, 2.19 fills; retrieval filters non-null |
| `embedding_model` | `String(128) NULL` |
| `embedding_dimensions` | `Integer NULL` |
| `text_tsv` | generated always as `to_tsvector('english', text)` stored; GIN index `ix_chunks_text_tsv` |
| — | HNSW index `ix_chunks_embedding` using `vector_cosine_ops` (m=16, ef_construction=64) |

Note: Phase-3 step 3.1's "migration adds tsvector + GIN + HNSW" is
**superseded** — those land here. Trim 3.1 when Phase 3 is sliced.

---

## JSON:API conventions — final

The small internal layer lives in `backend/app/api/jsonapi.py` (step 2.3).

- **Media type: plain `application/json`** carrying JSON:API 1.1 document
  structure (`data/attributes/relationships/included/meta/errors`) — no
  content negotiation. Deliberate simplification; simpler for openapi-fetch.
- Pagination `page[number]` / `page[size]` (default 100, max 100);
  `meta: {"totalCount": n}`. Default sort `-createdAt` on all lists.
- Errors: `{"errors": [{"status": "422", "code": "invalid-transition",
  "detail": "…"}]}`. The frontend branches on **status + `code`**, never on
  detail text.
- All Phase-2 endpoints (reads included — this is an admin-only surface):
  `Depends(current_admin)`; writes additionally `Depends(csrf_protect)`.
- Resource type names: `products`, `documents`, `product-images`,
  `operations`. Attributes camelCase; enum values as stored (lowercase
  snake, e.g. `in_review`).

**`products`** — *(note, Phase 2b, 2026-08-27: `manufacturer` is since
derived — the related `manufacturers` row's `name`, `null` when unassigned;
wire shape unchanged. See
[`../phase-2b/shared-knowledge.md`](../phase-2b/shared-knowledge.md).)* —
attributes: `name, slug, manufacturer, modelName, yearFrom,
yearTo, status, draftSpec, verifiedSpec, createdAt, updatedAt` (spec objects
use the camelCase spec shape above; `null` when absent). **No relationships /
includes in Phase 2** — operation state reaches the UI via `/api/operations`
(one small cached query serves every row; ui-spec §3.2), so the JSON:API
layer defers include machinery until a resource needs it.
Filter: `filter[status]` (comma-separated). Endpoints:

- `GET /api/products`
- `GET /api/products/{id}`
- `POST /api/products` — body attribute `{name}` → 201 `backlog` row
  (duplicate slug → 409, code `duplicate-model`). From step 2.14 on, the
  service auto-transitions the new row to `ingesting` and enqueues the job
  **after commit**; before 2.14 the row simply stays in `backlog`.
- `PATCH /api/products/{id}` — `status` (transition per matrix; transition to
  `ingesting` re-enqueues ingestion server-side, from 2.14) and/or
  `draftSpec` (full-object replace; upsert semantics — a missing draft row is
  created). Never accepts `verifiedSpec`.

**`documents`** — read-only; attributes: `sourceType, sourceUrl, sourceTitle,
contentMarkdown, fetchedAt, createdAt`; `filter[product]` **required** on
list; list ordering: Wikipedia first, then `createdAt`.

**`product-images`** — attributes: `sourceUrl, attribution, status,
variants: {thumb, card, detail}` (computed URLs), `createdAt`;
`filter[product]`; `PATCH` of `status` only — legal: `pending→approved`,
`pending→rejected`, `approved→rejected` (the UI uses only
`pending→rejected` this phase; the other two are deliberate
API-completeness, e.g. approval promotion and later un-publishing).

**`operations`** — read-only; attributes: `type, status, progress, message,
error, entityType, entityId, createdAt, startedAt, finishedAt`; filters
`filter[entityType]`, `filter[entityId]`, `filter[status]` (deliberate
API-completeness — the Phase-2 UI fetches the unfiltered list).

**Plain (non-JSON:API):** `/auth/*`, `GET /api/events` (SSE), `/media/*`
(static), `/health`, `/ready`.

---

## SSE / LISTEN-NOTIFY — final

- **One PostgreSQL channel: `app_events`.** Payload = JSON ≤ 1 KB, **ids
  only, never content** (8 KB NOTIFY limit); clients refetch via the API.
- Payload shapes:
  - `{"event": "operation.updated", "operationId": …, "entityType": …, "entityId": …}`
  - `{"event": "product.updated", "productId": …}`
  - `{"event": "document.updated", "productId": …, "documentId": …}`
  - (`chat.message.created` reserved for Phase 3.)
- **Commit first, then `pg_notify`.** Same ordering for task enqueue: commit,
  then `.kiq()`.
- **Emitters (pinned — an event without an assigned emitter is a bug):**
  - `operation.updated` — every `operation_service` state change (2.6).
  - `product.updated` — every `product_service.transition` status change,
    product creation, and `draftSpec` PATCH (emission wired in 2.6 once the
    NOTIFY helper exists; the ingestion job's transitions flow through the
    same service from 2.14). The backlog chip flipping `ingesting →
    in_review` live — the phase's demo moment — rides on this event.
  - `document.updated` — source-document row creation/replacement (2.14).
  - The image PATCH (2.9) emits `product.updated`; a second admin session's
    `["productImages"]` cache may go stale until refetch — accepted for a
    single-admin reality.
- `GET /api/events` (step 2.7): sse-starlette `EventSourceResponse`,
  `Depends(current_user)` via session cookie (the reason `SameSite=Lax` was
  frozen in Phase 1), SSE `event:` = event name, `data:` = payload JSON,
  ping every 15 s. The LISTEN loop uses a dedicated long-lived
  auto-reconnecting psycopg connection started in the FastAPI lifespan —
  never a pooled session.
- Frontend (`useServerEvents`, step 2.4) invalidation map:
  - `operation.updated` → invalidate `["operations"]` only (progress ticks
    must not refetch the products list; status flips arrive as
    `product.updated`)
  - `product.updated` → `["products"]`
  - `document.updated` → `["documents"]` + `["products"]`
- Additional binding requirements on the hook (ui-spec §3.3): export
  `useServerEventsStatus(): {connected: boolean}` via module state +
  `useSyncExternalStore`; on reconnect (`open` after `error`) invalidate
  `["products"]` + `["operations"]` (gap events are lost); native
  `EventSource` retry only — no custom backoff, **no polling anywhere**.

---

## Operation lifecycle & progress messages — final

`queued` (row created before enqueue) → `running` (task start, sets
`started_at`) → `succeeded` | `failed` (sets `finished_at`; failed sets
`error`). Ingestion progress milestones (pinned English messages):

| % | `message` |
|---|---|
| 5 | `Looking up Wikipedia` |
| 15 | `Searching the web` |
| 20–60 | `Fetching sources (n/m)` |
| 65 | `Processing images` |
| 80 | `Extracting specifications` |
| 90 | `Generating embeddings` |
| 100 | — (succeeded) |

Partial source failures append a warning to `message` and never fail the job;
**zero usable documents = deterministic failure** (no retry), motorbike back
to `backlog`.

---

## Taskiq wiring — final

- Broker: `backend/app/jobs/broker.py` —
  `taskiq_redis.ListQueueBroker(url=settings.redis_url)`; **no result
  backend** (PostgreSQL operations are the state).
- Task names: `demo.ping`, `ingestion.run`, `embeddings.rebuild`; one module
  per job family under `backend/app/jobs/`.
- Compose `app-worker`: same image/env/bind-mount as `app-web`,
  `entrypoint: []`, command
  `taskiq worker app.jobs.broker:broker app.jobs.demo app.jobs.ingestion app.jobs.embeddings`
  (module list grows per step), `depends_on: postgres (healthy), redis
  (started)`; **never runs migrations**.
- Retry policy — **pinned, verified against taskiq 0.12.5**: transient
  failures (network/5xx/LLM timeouts) raise the custom `TransientJobError`;
  the broker attaches
  `taskiq.middlewares.SmartRetryMiddleware(default_retry_count=3,
  default_delay=5, use_jitter=True, use_delay_exponent=True,
  max_delay_exponent=60, types_of_exceptions=[TransientJobError])` via
  `.with_middlewares(...)`, and retryable tasks carry the
  `retry_on_error=True` label on their `@broker.task` decorator. Exceptions
  not instances of `TransientJobError` are never retried (built-in type
  filter). Note: the backoff is delay×attempt capped at `max_delay_exponent`
  (+0–1 s jitter) — multiplicative, good enough; do not hand-roll a 2^n
  variant. Deterministic failures mark the operation `failed` and do not
  retry. No scheduler, no cancellation.

---

## Ingestion decisions — final

- Source order: (1) Wikipedia, (2) web search. **No in-page link following in
  Phase 2.** PDFs are skipped with a warning; Docling deferred.
- **Search provider default: Tavily** (`POST https://api.tavily.com/search`
  via HTTPX — no SDK dependency) behind a `SearchProvider` protocol;
  `SEARCH_PROVIDER=tavily`. Missing `TAVILY_API_KEY` → Wikipedia-only
  ingestion with a warning, not a failure. **Verified call shape
  (2026-08-26):** auth `Authorization: Bearer <TAVILY_API_KEY>` header (the
  legacy body-key form is deprecated — don't use it); JSON body
  `{"query": …, "max_results": 2, "search_depth": "basic"}`; response
  `results[]` with `title`, `url`, `content`, `score` — we consume `url` +
  `title` only and **never** set `include_raw_content` (pages are fetched
  ourselves for provenance + raw retention). Free tier: 1 000 credits/month,
  basic search = 1 credit.
- Query templates (template → `source_type` of its results):
  - product: `"{name}" motorcycle official specifications`
  - technical: `"{name}" technical data specifications`
  - magazine: `"{name}" review test`
  Top 2 per template, ≤ `INGESTION_MAX_WEB_DOCUMENTS` (6) total.
- Fetch limits: timeout 20 s, max 5 MiB, accepted content-type `text/html`
  only, follow redirects, 1 s per-domain politeness delay, User-Agent
  `MotorcycleBuyingAdvisor/0.1 (educational project)`.
- Wikipedia lookup (record the matched title in `source_title` so the admin
  sees what was matched; endpoints live-verified 2026-08-26):
  - search: `GET https://en.wikipedia.org/w/rest.php/v1/search/page?q={name}&limit=3`
    → best hit (`pages[].key`, `matched_title`)
  - article: `GET https://en.wikipedia.org/api/rest_v1/page/html/{key}` → trafilatura
  - image URL: `GET https://en.wikipedia.org/api/rest_v1/page/summary/{key}`
    → `originalimage.source` (the summary carries **no** file title and **no**
    licence data)
  - image **file title**: `GET https://en.wikipedia.org/w/api.php?action=query&titles={title}&prop=pageimages&piprop=name&format=json&formatversion=2`
    → `pages[0].pageimage` (prepend `File:`)
  - image **attribution**: `GET https://commons.wikimedia.org/w/api.php?action=query&titles=File:{name}&prop=imageinfo&iiprop=extmetadata&iiextmetadatafilter=LicenseShortName|Artist|Credit|UsageTerms|LicenseUrl&format=json&formatversion=2`
    → `pages[0].imageinfo[0].extmetadata`. **`Artist`/`Credit` values are
    HTML — strip tags before storing.** Stored `attribution` text is composed
    as `"{Artist stripped} · {LicenseShortName} · {LicenseUrl}"`; any missing
    piece is omitted; if everything is missing, store `attribution = null`
    (the UI renders its "unknown attribution" fallback and the admin judges
    the image in review).
- Data dirs (inside the existing `./backend:/app` bind mount — no compose
  volume changes; `backend/var/` gitignored):
  - raw sources: `DATA_DIR/sources/{motorbike_id}/{document_id}.html`
  - media: `MEDIA_DIR/motorbikes/{motorbike_id}/…`
- Image variants (WebP, quality 80, aspect preserved, width-capped):
  `thumb` 320 px, `card` 640 px, `detail` 1280 px. Served by FastAPI
  `StaticFiles` mounted at `/media`.

---

## LLM decisions — final

- Factory: `backend/app/llm/models.py` —
  `get_chat_model(model: str | None = None)` returning
  `langchain_openrouter.ChatOpenRouter` (official langchain-ai package, pin
  `langchain-openrouter>=0.2.8,<0.3`; supports `.with_structured_output()`
  — use `method="json_schema"`, and **list every property in the schema's
  `required`** (see the 2.17 landed decision: OpenAI/Azure reject a
  `json_schema` response format with an incomplete `required`, even without
  `strict`; optionality must be a `null` union) — and tool calling; auth via
  `OPENROUTER_API_KEY`; pass `app_url`/`app_title` instead of manual
  `HTTP-Referer`/`X-Title` headers). **Never the OpenAI API directly.** If
  OpenRouter cannot serve a needed capability, stop and report — do not wire
  another provider. *(Verified 2026-08-26:
  https://docs.langchain.com/oss/python/integrations/chat/openrouter)*
- Embeddings go through **OpenRouter's own `POST /api/v1/embeddings`**
  (OpenAI-shaped; verified 2026-08-26:
  https://openrouter.ai/docs/api/reference/embeddings). `langchain-openrouter`
  ships no embeddings class — `backend/app/llm/embeddings.py` wires
  `langchain_openai.OpenAIEmbeddings(model=settings.embedding_model,
  base_url="https://openrouter.ai/api/v1", api_key=<OPENROUTER_API_KEY>,
  check_embedding_ctx_length=False)`. The `check_embedding_ctx_length=False`
  flag is mandatory (LangChain otherwise pre-tokenizes input into token
  arrays that OpenAI-compatible gateways reject — langchain issue #35204).
  Fallback if the wrapper misbehaves on the pinned versions: a thin HTTPX
  call to the same OpenRouter endpoint (still OpenRouter, still LangChain
  `Embeddings`-shaped).
- Defaults via `.env`: `CHAT_MODEL=openai/gpt-4.1-mini`,
  `EMBEDDING_MODEL=openai/text-embedding-3-small` (served by OpenRouter,
  1536-dim **native** — do not pass a `dimensions` parameter; pass-through is
  undocumented and the native size already matches the column),
  `EMBEDDING_DIMENSIONS=1536`. Every embedding call path asserts
  `len(vector) == settings.embedding_dimensions` before writing.
- Prompts: Markdown + Jinja under `backend/app/llm/prompts/`; loader
  `backend/app/llm/prompts.py` with `StrictUndefined` (missing variable =
  exception, never silent).
- Extraction (step 2.17): Pydantic schema mirroring the frozen spec column
  set 1:1, all fields optional, units normalized by validators (hp → kW,
  etc.), via `with_structured_output`. Prompt `spec_extraction.md`: extract
  only from provided text, unknown = null, fetched content is **untrusted
  data** (baseline injection hygiene; full sweep in 5.1).
- Token budget: character-based, no tokenizer dependency — Wikipedia document
  first, each document head-truncated to 12 000 chars, total input capped at
  `EXTRACTION_MAX_INPUT_CHARS` (60 000).
- Langfuse: optional callback slot in the factory, config-gated; wired for
  real in Phase 5.

---

## Chunking & embedding decisions — final

- Chunking (2.18): `MarkdownHeaderTextSplitter` →
  `RecursiveCharacterTextSplitter` (`langchain-text-splitters`);
  `CHUNK_SIZE_CHARS=3200` (≈800 tokens), `CHUNK_OVERLAP_CHARS=400`;
  `heading_path` from the header split. Structural only — no semantic/LLM
  chunking.
- Embeddings (2.19): batched 64 texts/request; model + dimensions stored per
  chunk row. Guard at startup/rebuild: configured `EMBEDDING_DIMENSIONS` ≠
  `vector` column dimension → **loud failure** naming the required migration;
  never silent truncation. `app embeddings rebuild` = Taskiq job
  `embeddings.rebuild` tracked as an operation.

---

## Config keys (added to `.env.dist` + `backend/app/core/config.py`)

```text
2.10: DATA_DIR=/app/var/data · INGESTION_FETCH_TIMEOUT_SECONDS=20 · INGESTION_MAX_FETCH_BYTES=5242880
2.11: SEARCH_PROVIDER=tavily · TAVILY_API_KEY= · INGESTION_MAX_WEB_DOCUMENTS=6
2.12: MEDIA_DIR=/app/var/media
2.16: OPENROUTER_API_KEY= · CHAT_MODEL=openai/gpt-4.1-mini
2.17: EXTRACTION_MAX_INPUT_CHARS=60000
2.18: CHUNK_SIZE_CHARS=3200 · CHUNK_OVERLAP_CHARS=400
2.19: EMBEDDING_MODEL=openai/text-embedding-3-small · EMBEDDING_DIMENSIONS=1536
```

---

## New dependencies per step

Backend (`backend/pyproject.toml` + `uv.lock`; run `make build` after):

| Step | Adds |
|---|---|
| 2.5 | `taskiq`, `taskiq-redis` |
| 2.10 | `httpx` (promote to runtime if dev-only), `trafilatura` |
| 2.12 | `pillow` |
| 2.16 | `langchain`, `langchain-openrouter>=0.2.8,<0.3`, `jinja2` |
| 2.18 | `pgvector`, `langchain-text-splitters` |
| 2.19 | `langchain-openai` (embeddings wrapper only — chat stays on `ChatOpenRouter`) |

Frontend (`frontend/package.json`; run `make rebuild` for the node_modules
volume):

| Step | Adds |
|---|---|
| 2.13 | `react-markdown`, `remark-gfm`, `react-hook-form`, `zod`, `@hookform/resolvers` |

---

## Frontend conventions — final

File placement follows the landed Phase-1 convention (routes in
`frontend/src/routes/admin/*Route.tsx`, shared components flat in
`frontend/src/components/`, hooks in `frontend/src/hooks/`). Full component
inventory and layouts: [`ui-spec.md`](ui-spec.md).

**Hook files (pinned — one file per replacement step so stubs die
wholesale):**

| File | Exports | Stubbed in | Made real in |
|---|---|---|---|
| `frontend/src/hooks/useServerEvents.ts` | `useServerEvents`, `useServerEventsStatus` | — (real from day one) | 2.4 |
| `frontend/src/hooks/useProducts.ts` | `useProducts(statusFilter)`, `useCreateProduct()`, `useTransitionProduct()` + types `Product`, `ProductStatus`, `ProductFilters` | 2.8 | 2.15 (deleted wholesale) |
| `frontend/src/hooks/useOperations.ts` | `useLatestOperationsByEntity()` + type `Operation` | 2.8 | 2.15 (deleted wholesale) |
| `frontend/src/hooks/useProductReview.ts` | `useProduct(id)`, `useProductDocuments(id)`, `useProductImage(id)`, `useSaveDraftSpec(id)`, `useRejectImage()` + types `SourceDocument`, `ProductImage`, `DraftSpec` | 2.13 | 2.20 (deleted wholesale) |

**Query keys** (pinned in `frontend/src/queryKeys.ts`, created in 2.4;
invalidation always targets the prefix):

| Key | Query |
|---|---|
| `["products", "list", {status}]` | `GET /api/products` (+ filter) |
| `["products", "detail", id]` | `GET /api/products/{id}` |
| `["operations", "list"]` | `GET /api/operations` |
| `["documents", productId]` | `GET /api/documents?filter[product]=…` |
| `["productImages", productId]` | `GET /api/product-images?filter[product]=…` |

List hooks walk pages via `meta.totalCount` (page size 100, catalogue ceiling
~150 rows) — row 101 must not silently disappear.

`useSaveDraftSpec` **merges the last-fetched `draftSpec` with the form
values** before the PATCH — the endpoint is full-object replace and the form
edits only a subset of the frozen fields (ui-spec §8).

**Stub rules** (Phase-1 `useAuth` pattern: real `useQuery`/`useMutation`
results over fixture data, header comment naming the deleting step;
components written against a stub must survive its replacement unchanged):

- **2.4 — no stub.** `useServerEvents` is real; an unreachable `/api/events`
  just makes `EventSource` retry silently. Tests mock `EventSource`.
- **2.8 — `useProducts.ts` + `useOperations.ts` stubs.** Fixtures: one
  product per status; the `useOperations` stub maps the `ingesting` bike's id
  to `{status: "running", progress: 40, message: "Fetching sources (2/6)"}`
  and one `backlog` bike's id to a `failed` operation (exercises the retry
  affordance).
- **2.13 — `useProductReview.ts` stub.** Fixtures: one Markdown document with
  headings **and a GFM table** (proves the react-markdown config), a full
  `draftSpec` with some nulls (proves the form's null handling), one
  `pending` image with attribution.
- Type regeneration command: `pnpm generate:api` (needs `app-web` up) —
  first action of 2.15 and 2.20.

---

## Landed decisions

Appended by implementing agents when a step finishes — decisions later steps
depend on. 1–3 bullets per step, no prose.

### Step 2.1 (catalogue models & services)

- **Service contracts** (all module-level, `AsyncSession` first):
  `product_service.slugify(name)`, `create_backlog(session, name)` →
  `DuplicateModelError` (carries the slug in `args[0]`),
  `transition(session, motorbike, new_status)` → `InvalidTransitionError`
  (`.current` / `.requested`, `str(error)` is a ready 422 detail),
  `upsert_draft_spec(session, motorbike_id, values: Mapping[str, Any])`;
  `document_service.create_document(session, motorbike_id, *, source_type,
  source_title, raw_path, content_markdown, fetched_at, source_url=None)` and
  `list_for_motorbike(session, motorbike_id)`. Public functions **commit**;
  private helpers (`_apply_approval`, `_upsert_spec`) deliberately do not, so
  approval stays one transaction. `LEGAL_TRANSITIONS` is the exported matrix —
  status changes go through `transition`, never `motorbike.status = …`.
- **Spec writes are keyed on `motorbike_spec.SPEC_FIELDS`** (the frozen column
  set, table order; also `SPEC_CATEGORIES` / `PRICE_BANDS` for the pinned
  vocabularies). `values` is full-object: omitted fields are reset to NULL
  (`extra` to `{}`), a key outside `SPEC_FIELDS` raises `ValueError` (bug, not
  user input — 2.3's Pydantic schema is the boundary). `a2_eligible` is derived
  in `_resolve_a2_eligible` (skipped when `wet_weight_kg <= 0`); approval
  re-runs it while promoting draft → verified. `motorbike_specs` deliberately
  has **no `created_at`/`updated_at`** — only `extracted_at`.
- Migration `4ea01933a43b` (all four tables) leaves head at `4ea01933a43b`;
  its downgrade drops the four native enum types explicitly (as in
  `f68e3fe43b2d`) — copy that when adding `operations`/`chunks`. Documents are
  ordered by `source_type != 'wikipedia'` then `created_at` (false sorts
  first) — reuse that expression for the 2.9 list endpoint.
  `tests/services/conftest.py`'s `FakeAsyncSession` now interprets any mapped
  entity plus `select`/`delete`/`update`, `AND`-ed `==`/`!=` where-clauses and
  `order_by` (`.store()` / `.rows(Model)` accessors; server defaults are **not**
  simulated — services set enum defaults in Python, tests stamp `created_at`).

### Step 2.4 (SSE client hook & query keys)

- `frontend/src/queryKeys.ts` exports one `queryKeys` object; every query uses
  its builders (`products.list(status?)`, `products.detail(id)`,
  `operations.list()`, `documents.byProduct(id)`,
  `productImages.byProduct(id)`) and every invalidation targets the sibling
  prefix (`queryKeys.<resource>.all`) — never a hand-typed array.
- `useServerEvents()` invalidates through `useQueryClient()` (the provider's
  shared client, per the Phase-1 hook convention) and is mounted by the local
  `ServerEventsConnection` component inside `AppLayout`, gated on
  `useAuth().user`; `useServerEventsStatus()` reads module state and reports
  `{connected: false}` before the first `open` and whenever nothing is mounted,
  so 2.8's warning Alert needs its 5 s grace timer to cover initial connect.
- Stream URL is `${import.meta.env.VITE_API_URL ?? ""}/api/events` with
  `{ withCredentials: true }`, mirroring `api/client.ts`'s baseUrl (dev is
  cross-origin :5173 → :8000; production same-origin resolves to the pinned
  `/api/events`) — 2.7 must therefore keep the endpoint inside the
  credentials-allowing CORS config.

### Step 2.5 (Taskiq broker & worker service)

- **One deviation from the pinned broker call, required by redis-py 8.1:**
  `ListQueueBroker(url=…, socket_timeout=None)`. redis-py ≥ 8 defaults
  connections to `socket_timeout=5` while `ListQueueBroker.listen()` issues an
  infinite `BRPOP`; the blocking read then raises `redis.TimeoutError`, which
  taskiq-redis 1.2.3 does not catch (`ConnectionError` only), so every worker
  process — plus whatever task it was running — died every 5 idle seconds
  (verified: 18 `worker is dead. Scheduling reload.` lines in 90 s; 0 after the
  fix). Do not remove the kwarg; do not pin `redis<8` instead.
- Job modules import `broker` from `app.jobs.broker` and raise
  `app.jobs.TransientJobError` (defined in `jobs/__init__.py`, so job modules
  need not import the Redis wiring) for anything retryable; every task gets
  `@broker.task("<family>.<name>", retry_on_error=True)`. Task names are
  positional, matching the pinned `demo.ping` / `ingestion.run` /
  `embeddings.rebuild`. The broker keeps taskiq's `DummyResultBackend` — never
  call `.wait_result()`.
- CLI enqueue contract (`app/cli/jobs.py`, follow it for `app ingest run` /
  `app embeddings rebuild`): sync Typer body → `asyncio.run(_impl())`; `_impl`
  does `await broker.startup()` → `await <task>.kiq(...)` → `await
  broker.shutdown()` in a `finally`, prints the returned `task_id`, waits for
  nothing. Tests stub `app.cli.jobs.broker` and the task object by name
  (`tests/cli/test_jobs.py`), so no test needs Redis. Each new job family also
  gets its module appended to `app-worker`'s command in `compose.yaml`.

### Step 2.8 (backlog screen, UI-only)

- **Error contract for products calls:** `hooks/useProducts.ts` exports
  `ProductError` (`status: number`, Phase-1 `AuthError` shape) and screens map
  **status codes only** (409 → duplicate, 422 → name error, else
  `common.errors.serverError`). Step 2.15 must keep this export and build it
  from the JSON:API error object (`status`, and `code` if it adds it); the
  stubs additionally keep an in-memory table, so add/retry visibly change rows
  until 2.15.
- **Component contracts (written to survive 2.15/2.13 unchanged):**
  `EmptyState({icon,title,body,action?})` takes *already translated* strings;
  `MotorbikeStatusChip({status})` and `OperationProgress({operation,name,onRetry?})`
  import `ProductStatus` / `Operation` from the hook files — 2.15/2.20 must
  re-export those type names. `OperationProgress` takes
  `Pick<Operation,"status"|"progress"|"message">`, returns `null` on
  `succeeded`, and renders its own retry button only when `onRetry` is passed
  (the backlog does not: retry lives in the Actions column).
  `AddModelDialog({onClose,onCreated})` is **rendered conditionally** with
  `<Dialog open>` (mount-per-opening discards stale input); the route owns
  closing and clearing the `status` param.
- **Timer-reset pattern + omissions:** eslint `react-hooks/set-state-in-effect`
  forbids the "reset state in an effect" idiom, so the 5 s SSE grace timer is a
  local `LiveDisconnectAlert` component that `AdminLayout` mounts only while
  `connected === false` — unmount resets the grace. Reuse that pattern instead
  of a reset effect. Deliberately omitted: no error surface for the row
  transition mutation (ui-spec defines none), and `admin.review.*` i18n keys
  landed verbatim from ui-spec §10 with `priceBandValues`/`categoryValues`
  still empty for 2.13 to fill.

### Step 2.3 (JSON:API layer & `/api/products`)

- **`app/api/jsonapi.py` is what 2.6/2.9 reuse verbatim:** `Resource[Attrs]`,
  `Document[Res]`, `ListDocument[Res]` (PEP 695 generics — subclass them per
  resource, e.g. `class ProductDocument(Document[ProductResource])`, so OpenAPI
  gets clean component names), `Meta(total_count)`, `jsonapi.PaginationDep`
  (`page[number]`/`page[size]`, `.limit`/`.offset`), `parse_filter(raw) ->
  list[str] | None`, `JsonApiError(status_code, code, detail)`,
  `error_responses(*codes)` for the `responses=` OpenAPI docs. Request
  envelopes are **not** generic — each resource spells out
  `…CreateRequest`/`…PatchRequest` with `extra="forbid"` at every level and
  `type: Literal["<resource>"]` defaulted (that `extra="forbid"` is what turns
  `verifiedSpec` in a PATCH body into a 422).
- **Error-shape split (follow it, the SPA branches on it):** domain failures
  render as the JSON:API `errors[]` document via `JsonApiError` (handler
  registered once in `main.py`) — `404 not-found`, `409 duplicate-model`,
  `422 invalid-transition`, `400 invalid-filter` (unknown `filter[status]`
  member); request/body validation keeps FastAPI's default
  `422 {"detail":[{"loc":…}]}` (ui-spec §8 maps `loc` to fields) and
  `current_admin`/`csrf_protect` keep their `{"detail": "…"}` 401/403. Routers:
  `APIRouter(prefix="/products", tags=[…], dependencies=[Depends(current_admin)])`
  plus `Depends(csrf_protect)` per write, included in `main.py` with
  `prefix="/api"`; `api/endpoints/__init__.py` and `api/schemas/__init__.py`
  stay pure package markers (Phase-1 convention).
- **New `product_service` read functions — reuse, don't re-query:**
  `get_motorbike(session, id)`, `list_motorbikes(session, *, statuses=None,
  limit, offset) -> (rows, total)` (order `created_at DESC, id DESC`),
  `get_specs(session, ids) -> {motorbike_id: {SpecKind: row}}`. **After any
  write a route must `await session.refresh(row)` before rendering**:
  `motorbikes.updated_at` has a server-side `onupdate`, so the flush expires the
  attribute and rendering it is implicit IO → `MissingGreenlet` 500. The
  fake-session tests cannot reproduce this — prove writes with real-DB curl.
- Spec payload split: `SpecAttributes` (read; `float` for the Numeric columns so
  JSON carries numbers, `SpecCategory`/`PriceBand` enums) vs `DraftSpecRequest`
  (write; `gt=0` plus column ceilings, all 16 frozen fields accepted so the
  SPA's merge-and-replace survives). `DraftSpecRequest.model_dump()` *is* the
  service's full-object mapping. PATCH applies `draftSpec` before `status`, so
  one request that saves and approves promotes the values it just sent. No
  enqueue on create (2.14), no relationships/includes.

### Step 2.6 (operations, NOTIFY, `/api/operations`)

- **`operation_service.notify(session, payload)` is the project's only writer to
  `app_events`** — every future emitter (2.9 images, 2.14 documents, Phase 3)
  calls it, never `pg_notify` directly; `EVENT_CHANNEL` and
  `MOTORBIKE_ENTITY_TYPE = "motorbike"` are exported from there too (2.7's LISTEN
  loop should import `EVENT_CHANNEL`). It `execute`s the `pg_notify` **and
  commits it**, because a notification is only delivered when its own transaction
  commits — so a state change costs two commits: the data one, then the
  announcement (the pinned "commit first, then notify" ordering is exactly this).
  Consequence for tests: `FakeAsyncSession.commit_count` counts both, and
  `tests/services/conftest.py` now interprets `select(func.pg_notify(...))` into
  `.notifications` (`[(channel, payload)]`) so ordering is observable.
- **Lifecycle contract** (`operation_service`, `AsyncSession` first, all commit +
  announce): `create(session, type, *, entity_type=None, entity_id=None)` →
  `queued`/progress 0, `start` (→`running`, stamps `started_at`), `advance(…,
  progress, message=None)` (progress only, status untouched; `ValueError` outside
  0–100), `succeed` (progress 100 + `finished_at`), `fail(…, error)` (keeps the
  progress reached, so how far a job got survives), plus
  `list_operations(session, *, entity_types, entity_ids, statuses, limit, offset)`
  ordered `created_at DESC, id DESC`. `message`/`error` are truncated to their
  column widths. No status matrix (unlike products) and deliberately **no
  `get(session, id)`** — 2.14 adds it when the worker needs to reload a row.
- `product_service` now announces `{"event":"product.updated","productId":…}`
  after every commit in `create_backlog`, `transition` and `upsert_draft_spec`
  (private `_announce`, id captured *before* the commit); a PATCH that sends both
  `draftSpec` and `status` therefore emits twice — invalidation is idempotent.
  `_get_by_slug` became public `get_by_slug` for `app operations demo --bike`.
- `GET /api/operations` is read-only (no POST/PATCH route at all → 405),
  `Depends(current_admin)`, filters `filter[entityType]`/`filter[entityId]`/
  `filter[status]` all comma-separated via `jsonapi.parse_filter` (unknown status
  → 400 `invalid-filter`, like products); `updated_at` is deliberately **not** an
  exposed attribute. `app operations demo [--bike <slug>]` walks
  queued→running→6 pinned ingestion milestones→succeeded at
  `STEP_SECONDS = 1.0` (unknown slug → stderr + exit 1).

### Step 2.7 (SSE endpoint & LISTEN fan-out)

- **`app/services/notification_listener.py` owns the only consumer of
  `app_events`:** `NotificationListener(connect=None, *, channel=EVENT_CHANNEL)`
  with `start()` (sync — spawns the task, never waits for the database, so a
  down PostgreSQL cannot delay or fail startup), `await stop()` (cancel + drop
  subscribers, idempotent), `subscribe() -> asyncio.Queue[Event]`,
  `unsubscribe(queue)` (idempotent), `subscriber_count`. `Event` is
  `(name, data)` = payload `event` member + the payload JSON verbatim; the
  listener parses once and drops unusable payloads with a warning. Reconnect is
  exponential 1 s → 30 s, re-issuing `LISTEN`; the dedicated connection comes
  from `psycopg.AsyncConnection.connect(<database_url minus +psycopg>,
  autocommit=True)` — never a pooled session. Per-subscriber queue holds 100
  events and drops its **oldest** when a client stops reading (ids only, clients
  refetch). Injectable `connect` factory is how tests drive it without a DB.
- **The listener lives on `app.state`:** `main.lifespan` creates it and parks it
  under `app/api/endpoints/events.py:LISTENER_STATE_ATTRIBUTE`
  (`"notification_listener"`); the endpoint reads it from `request.app.state` and
  answers `503 {"detail": "Event stream unavailable."}` if it is absent (only a
  process without lifespan — a *reconnecting* listener keeps the stream open and
  pinging). `/health` and `/ready` are untouched by listener state; `/ready`
  keeps its existing PostgreSQL-only contract.
- `GET /api/events` = `APIRouter(prefix="/events", tags=["events"],
  dependencies=[Depends(current_user)])` mounted with `prefix="/api"` (inside the
  credentials-allowing CORS config, per 2.4), `EventSourceResponse(..., ping=15)`,
  `ServerSentEvent(event=<name>, data=<payload JSON>)`, subscriber queue removed
  in the generator's `finally`. `sse-starlette~=3.4.0` was already a dependency —
  nothing added to `pyproject.toml`/`uv.lock`, no `make build` needed.

### Step 2.9 (documents & product-images endpoints)

- **Image moderation lives in `product_service`** (it already owned
  `MotorbikeImage` through `_apply_approval`): `LEGAL_IMAGE_TRANSITIONS`
  (`pending→{approved,rejected}`, `approved→{rejected}`, `rejected→{}`),
  `InvalidImageTransitionError(current, requested)` (`str(error)` is a ready 422
  detail), `transition_image(session, image, new_status)` (commits, then
  announces `product.updated` via the existing private `_announce`),
  `get_image(session, image_id)` and `list_images(session, *, motorbike_id=None)`
  (order `created_at DESC, id DESC`). No `refresh` needed after the image write —
  `motorbike_images` has no server-side `onupdate` column and the sessionmaker
  sets `expire_on_commit=False`. 2.12 must keep writing image rows through a
  service, never flip `image.status` directly.
- **Both lists are deliberately unpaginated** (no `page[number]`/`page[size]`
  params): documents reuse `document_service.list_for_motorbike` verbatim with
  its pinned ordering, images are ≤1 row per ingestion run, and ui-spec §7 wants
  the complete document list for its picker. `meta.totalCount` is therefore the
  number of rows returned. `filter[product]` is **required** on `/api/documents`
  (absent → 400 `missing-filter`, a new error code) and **optional** on
  `/api/product-images` (absent = whole catalogue); on both, more than one
  comma-separated member → 400 `invalid-filter`. `rawPath` (documents) and
  `originalPath` (images) are never exposed.
- **The variant URL formula lives in `app/api/schemas/images.py`**:
  `MEDIA_URL_PREFIX = "/media"` plus `variant_urls(motorbike_id, image_id) ->
  ImageVariants` whose field names (`thumb`/`card`/`detail`) *are* the variant
  names — `/media/motorbikes/{motorbike_id}/{image_id}_{variant}.webp`, computed
  per response, no disk access. 2.12 writes the matching
  `MEDIA_DIR/motorbikes/{motorbike_id}/{image_id}_{variant}.webp` files and must
  keep the two in sync (the API layer stays import-free for jobs).

### Step 2.15 (backlog wired live)

- **Envelope unwrapping happens in the hooks and nowhere else:** `Product` is
  `{ id: string } & components["schemas"]["ProductAttributes"]` and `Operation` is
  `{ id: string } & components["schemas"]["OperationAttributes"]` — no component
  ever touches `.attributes` (so `draftSpec`/`verifiedSpec` already ride along on
  `Product`). 2.20's `useProductReview` should flatten `documents` /
  `product-images` the same way.
- `ProductError` keeps `status` and gains `code: string | null` — `errors[0].code`
  of a JSON:API error document, `null` for the shapes that carry none (FastAPI's
  request-validation 422, auth/CSRF `{"detail": …}`); screens still branch on
  `status`. `useOperations` deliberately exports **no** error type (plain `Error`
  with the status in the message): no screen branches on why progress is missing.
- **The page walk is copied inline into each list hook** (`PAGE_SIZE = 100`; loop
  until `rows.length >= data.meta.totalCount` or an empty page arrives) — no
  shared pagination helper module; repeat the loop in 2.20's list hooks.
- `pnpm generate:api` shells `docker compose exec app-web`, which fails whenever
  app-web's *image* predates a backend dependency (taskiq, here). Equivalent and
  image-independent: `docker compose run --rm -T app-cli app openapi export >
  frontend/openapi.json` then `docker compose run --rm -T node-cli pnpm exec
  openapi-typescript openapi.json -o src/api/schema.d.ts` (verified byte-identical
  to `GET /openapi.json`).
- The 2.8 component/route tests now run against `stubFetch` JSON:API fixtures
  instead of stub-hook fixtures — `AdminBacklogRoute.test.tsx` carries a tiny
  in-memory products/operations API whose status `PATCH` really moves its row.
  **No component source changed**, so the 2.8 stub contract held.

### Step 2.10 (fetch & extract core)

- **HTTPX is the `httpx2` distribution** (`import httpx2`): HTTPX 2.x ships under
  that name and was already installed as fastapi.testclient's dependency, so
  "promote httpx to runtime" landed as moving `httpx2~=2.0.0` from the dev group
  into `[project].dependencies` — no second HTTP client was added. 2.11's Tavily
  call must `import httpx2` and should reuse `fetch.build_client()`.
- **Fetch/extract never raise for an expected outcome — they return a typed
  failure**, so the caller picks the severity: `fetch.fetch_html(url, *,
  client=None, gate=None) -> FetchResult | FetchFailure` (`FetchResult.url` is
  the post-redirect URL, `.content` the retained bytes, `.text` the decoded
  payload; `FetchFailure.reason` is `FetchFailureReason`
  `invalid_url|timeout|network_error|http_error|unsupported_content_type|too_large`
  plus a warning-ready `.detail` — a 4xx/5xx status is a failure, not a result)
  and `extract.extract_markdown(html, *, url=None) -> ExtractResult |
  ExtractFailure` (`ExtractFailureReason.EMPTY`). Every failure is logged once as
  a `logger.warning` inside the module, so callers only need to decide, not log.
  `fetch.build_client()` carries the pinned limits (reuse one client per
  ingestion run); the process-wide `fetch.politeness` gate reserves a per-host
  slot under a lock and sleeps outside it (clock + sleep injectable).
- **Raw payloads:** `storage.save_raw_document(motorbike_id, document_id,
  payload, *, data_dir=None) -> str` returns exactly the `source_documents.
  raw_path` value (`sources/{motorbike_id}/{document_id}.html`, DATA_DIR-relative
  — `storage.resolve(path)` maps it back); ids must therefore exist before the
  payload is written, and `document_id` reuse overwrites in place.
  `extract.normalize()` output is what 2.18 chunks: `#` ATX headings and GFM
  tables preserved, CRLF/NBSP/trailing spaces removed, no run of >2 newlines.
  Headings needed a follow-up fix to be true for real Wikipedia HTML — see
  "Step 2.18 follow-up (heading extraction fix)" at the bottom of this section.
  Deliberate omissions: no `title` from extraction (search/Wikipedia supply
  `source_title`), no CLI test file (`app ingest fetch-url` is the manual smoke
  tool; it writes under `sources/cli/`), no in-page link following.

### Step 2.11 (Wikipedia + web search adapters)

- **`wikipedia.py` contract 2.14 builds on** (all `*, client=None, gate=None`,
  reuse one `fetch.build_client()` per run): `lookup(name) -> WikipediaResult |
  WikipediaFailure` runs the whole chain, or compose it —
  `find_page(name) -> WikipediaPage | WikipediaFailure`,
  `fetch_article(page) -> WikipediaArticle | WikipediaFailure`,
  `find_image(page) -> WikipediaImage | None`. `WikipediaPage` = `key` (REST path
  segment) + `title` (**`matched_title or title` of the best hit — store as
  `source_documents.source_title`**) + `url` (`…/wiki/{key}`, the human page, →
  `source_url`, never the REST endpoint we fetched); `WikipediaResult` =
  `page, content` (raw bytes → `storage.save_raw_document`), `markdown` →
  `content_markdown`, `image`. Typed reasons: `no_match` (deterministic — the
  admin's name matched nothing) vs `search_failed` / `article_fetch_failed` /
  `extraction_failed`. A missing image or missing licence data is never a
  failure: `None` image, or an image with `attribution=None`.
- **`search.py` contract:** `get_search_provider() -> SearchProvider` (protocol,
  one method `search(name, *, client=None, gate=None) -> SearchResults`);
  `SearchResults(candidates: tuple[SearchCandidate, ...], warnings:
  tuple[str, ...])` where `SearchCandidate` is `url, title` (falls back to the
  URL — `source_title` is NOT NULL) and `source_type` **taken from the query
  template**, and `warnings` are the strings the job appends to the operation
  message (missing `TAVILY_API_KEY`, a failed query) — a provider never raises
  for an expected outcome. Candidates are deduped by URL keeping the first
  (product) label and capped at `INGESTION_MAX_WEB_DOCUMENTS`; the cap also stops
  further queries, so credits are not spent past it. Config keys landed:
  `SEARCH_PROVIDER` (typed `config.SearchProviderName = Literal["tavily"]`),
  `TAVILY_API_KEY`, `INGESTION_MAX_WEB_DOCUMENTS`.
- **JSON endpoints bypass `fetch_html`** (it is `text/html`-only): each module has
  its own thin helper (`wikipedia._get_json`, `TavilySearchProvider._post`) that
  reuses the passed client — hence the pinned User-Agent — and the same
  `fetch.politeness` gate (Tavily's host included), and returns `None` after one
  logged warning for timeout/network/≥400/non-JSON. One live-verified caveat for
  2.14/QA: the pinned "best hit = `pages[0]`" is Wikipedia's ranking, and for
  `"Suzuki GSR 600"` (with the space) it ranks the manufacturer article *Suzuki*
  first, while `"Suzuki GSR600"` matches the model — the recorded `source_title`
  is exactly the disambiguation guard for that. Deliberate omissions: `Credit` /
  `UsageTerms` are requested per the pinned extmetadata filter but are not part
  of the composed attribution string; no CLI test file (`app ingest probe` is the
  manual smoke tool, DB-free).

### Step 2.16 (LLM foundation)

- **`app/llm/models.py` is the only place a chat model is built:**
  `get_chat_model(model: str | None = None) -> ChatOpenRouter` (signature exactly
  as pinned — bind extra kwargs on the returned model, don't widen it) passing
  `model=model or settings.chat_model`, `api_key=settings.openrouter_api_key`,
  `app_url=APP_URL` / `app_title=APP_TITLE` (module constants: repo URL +
  "Motorcycle Buying Advisor", deliberately not config — attribution is
  environment-independent), and `callbacks=observability_callbacks(settings) or
  None`. `observability_callbacks(settings) -> list[BaseCallbackHandler]` is the
  **Langfuse slot**: it returns `[]` today; Phase 5 adds the `LANGFUSE_*` gate
  inside it and every existing call site is traced unchanged. An empty
  `OPENROUTER_API_KEY` raises `models.MissingApiKeyError` (message
  `"OPENROUTER_API_KEY is not configured."`) instead of a pydantic
  ValidationError — jobs/CLI catch that type to report configuration, not bugs.
- **Prompts:** `app/llm/prompts.py` exposes `render_prompt(name, /, **variables)`
  (positional-only name, `.md` suffix optional) over an `lru_cache`d Jinja
  `Environment` (`StrictUndefined`, `autoescape=False` — Markdown to a model, not
  HTML to a browser, `trim_blocks`/`lstrip_blocks` on) rooted at
  `prompts.PROMPTS_DIR` = `app/llm/prompts/`. Missing variable →
  `jinja2.UndefinedError`, unknown name → `jinja2.TemplateNotFound`; both are
  treated as programming errors, never caught for user input. The module
  `prompts.py` and the sibling directory `prompts/` coexist on purpose (the
  module wins the import); 2.17's `spec_extraction.md` just drops into the
  directory. `ping.md` is the trivial prompt used by `app llm ping` and the tests.
- **CLI `app llm`** (`app/cli/llm.py`, registered in `cli/main.py`): `ping
  [--model]` (renders `ping.md`, one `ainvoke`, prints model on stderr + reply on
  stdout) and `embeddings-smoke [--model]` (thin `httpx2` POST to
  `openrouter.SERVERS[openrouter.SERVER_PRODUCTION]` + `/embeddings`, asserts
  `len(vector) == 1536`). Both fail fast with a one-line stderr message + exit 1
  for a missing key; `ping` also maps `openrouter.errors.OpenRouterError` to one
  line. The smoke command carries `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS` as
  module constants — **2.19 must move them to config and delete the constants.**
- **Embeddings smoke result: BLOCKED — `OPENROUTER_API_KEY` is not set in the
  root `.env`, so neither the live `ping` nor the 1536-dimension assertion has
  run.** What *is* verified: the route exists and is OpenAI-shaped (`POST
  https://openrouter.ai/api/v1/embeddings` answered `401 {"error":{"message":
  "Missing Authentication header"}}` for a bogus key, identical to curl) and the
  chat path reaches OpenRouter (SDK `UnauthorizedResponseError`). Re-run both
  commands as the first action of any step that needs a real completion.
- **Lock side effect of `langchain~=1.0`:** `langgraph-sdk` (pulled in
  transitively) caps `websockets<17`, so `uv lock` downgraded uvicorn's
  `websockets` 17.0.1 → 16.1.1. Verified harmless: uvicorn 0.52.4 boots the app in
  the rebuilt image and `/health` answers 200. Don't "fix" the downgrade.

### Step 2.12 (image pipeline & `/media`)

- **`image_service.ingest_image(session, motorbike_id, image_url,
  attribution=None, *, client=None, gate=None, media_dir=None) -> ImageResult |
  ImageFailure`** is what 2.14 calls **once per run**: it downloads, retains the
  original, writes the three variants and **commits** the `pending` row (no
  NOTIFY — image/document creation events are 2.14's). `ImageResult` carries
  `image` (the row), `original_path` and `variant_paths` (variant name →
  MEDIA_DIR-relative path); `ImageFailure(url, reason, detail)` with
  `ImageFailureReason` `download_failed | unsupported_content_type |
  unreadable_image` is **already logged once** — the job only appends `detail` to
  the operation message, never raises. Path helpers (MEDIA_DIR-relative, mirroring
  `storage.py`): `motorbike_directory`, `variant_path(motorbike_id, image_id,
  variant)`, `original_path(…, suffix)`, `resolve(path, *, media_dir=None)`, plus
  `VARIANT_WIDTHS = {"thumb": 320, "card": 640, "detail": 1280}` — the disk half
  of the pinned formula, kept in sync with `app/api/schemas/images.py` by
  `tests/services/test_image_service.py::test_variant_paths_are_the_paths_of_the_api_variant_urls`.
- **The download half copies the fetch layer rather than extending it** (same
  split as `wikipedia._get_json`): a private `_download`/`_stream` reusing
  `fetch.ALLOWED_SCHEMES`, `fetch.build_client`, `fetch.politeness`,
  `fetch.FetchFailure` and `INGESTION_MAX_FETCH_BYTES`, with a pinned
  content-type allowlist `image/jpeg|png|webp|gif` (the declared type only names
  the retained original's suffix — the decoder decides what the bytes are).
  Pillow runs in `asyncio.to_thread`; EXIF orientation is applied once,
  transparency preserved (`RGBA`) instead of flattened, and a variant is a **cap,
  never an upscale** (a 200 px source yields three 200 px files, all three paths
  always exist). Original is `{image_id}_original{.jpg|.png|.webp|.gif}` — never
  served to the browser, but reachable under `/media` by construction.
- **`/media` is `StaticFiles(directory=settings.media_dir, check_dir=False)` with
  no `mkdir`:** `create_app()` must have zero filesystem side effects (an mkdir of
  the container path `/app/var/media` made every host-side `create_app()` raise
  `PermissionError` → 129 test errors); the directory appears when the first image
  is stored, until then media URLs are 404. `main.py` also calls
  `mimetypes.add_type("image/webp", ".webp")` — Python 3.12 + the slim image know
  no `.webp` and would serve every variant as `application/octet-stream`. Config
  `MEDIA_DIR=/app/var/media`, dependency `pillow~=12.3.0`; `main.py` deliberately
  imports neither Pillow nor `image_service`, so app-web boots on an image without
  Pillow. Dev command: `app ingest fetch-image <url> <bike-id> [--attribution]`
  (unknown id → stderr + exit 1, no FK traceback).

### Step 2.13 (review screen, UI-only)

- **`useProductReview.ts` stub contract 2.20 must preserve verbatim:**
  `useProduct(id) -> UseQueryResult<Product>` (`Product` imported from
  `useProducts.ts`, key `products.detail(id)`), `useProductDocuments(id) ->
  SourceDocument[]`, `useProductImage(id) -> ProductImage | null` (null = no image
  row), `useSaveDraftSpec(id).mutate({ values: Partial<DraftSpec> })` (the hook
  merges with the last-fetched draft and invalidates **only**
  `products.detail(id)`), `useRejectImage().mutate({ imageId, productId })`. Types
  `DraftSpec = components["schemas"]["SpecAttributes"]`, hand-written
  `SourceDocument`/`ProductImage`/`SourceType`/`ImageStatus` (documents & images are
  not in the schema this step generated against), plus
  `SaveDraftSpecError(status, validationFields)` — the `AuthError` shape; the specs
  form maps `validationFields` onto its fields and falls back to a general Alert, so
  2.20 must fill it from the 422 `loc` tails.
- **Component contracts (written to survive the 2.20 stub deletion):**
  `ConfirmDialog({title, body, warning?, confirmLabel, confirmColor?, isPending?,
  hasError?, onConfirm, onClose})` takes *already translated* strings (only
  `admin.review.actions.actionError` is its own) and is rendered conditionally with
  `<Dialog open>` like `AddModelDialog`. All three panels take `product: Product`
  and own their own query (loading/error are page-level, so a panel renders `null`
  until data is there); `ModelSpecsPanel` additionally takes
  `onDirtyChange(isDirty)` — the route owns the dirty flag for the approve dialog's
  `unsavedWarning`, and the panel reports `false` on unmount, i.e. switching tabs
  drops the form buffer by design. Markdown goes through `react-markdown` +
  `remark-gfm` with an `ExternalLink` renderer for `a`; raw HTML stays off (never
  add `rehype-raw`).
- **Deliberate choices/omissions:** the read-only `extra` table renders in *both*
  draft and verified mode (§8's extra block is not status-scoped); the fixture set
  is a superset of the pinned minimum — a second (magazine) document exists so the
  `?doc=` selection contract is exercisable; the Zod schema stays module-private
  (exporting it would trip `react-refresh/only-export-components`) and is tested
  through the rendered form with a doubled save mutation; `i18n`
  `priceBandValues`/`categoryValues` are now filled from the pinned vocabularies.
  Ordering consequence of 2.15 landing first: approve/reject `PATCH` hit the real
  API while the review data is fixture, so after a successful approve the chip does
  **not** flip until 2.20 makes `useProduct` real — gates are reached by editing
  `FIXTURE_PRODUCT.status`.
- **Dependency-change mechanics for frontend steps (node-cli's `node_modules` is an
  anonymous volume from the *image*):** `docker compose run --rm node-cli pnpm
  install` does not reach the running dev server, and pnpm refuses to install into
  the bind-mounted `/app` (store-location clash). Working sequence used here:
  `pnpm add --save-exact …` on the host (pnpm 11.17.0 / Node 24 match the image, so
  the lockfile stays valid) → `docker compose build frontend node-cli` →
  `docker compose up -d --force-recreate --renew-anon-volumes frontend`. No
  `make rebuild` needed, and other services stay untouched.

### Step 2.14 (ingestion orchestration job)

- **Contracts 2.17/2.19 build on:** `app/services/ingestion/service.py` exposes
  `ingest(session, motorbike, operation, *, client=None, gate=None)` (one
  `fetch.build_client()` per run, reused by every adapter) and
  `abandon(session, motorbike, operation, error)` (bike → `backlog` **only if
  still `ingesting`**, then operation `failed`); a new stage goes between
  `_Run._image_stage` and `_Run._complete`, reporting through
  `_Run._advance(progress, message)` and `_Run._warn(detail)`. The task is
  `ingestion.run(motorbike_id: str, operation_id: str)` — ids only, its own
  session; it re-raises `TransientJobError` untouched and, for any other
  exception, rolls back → `abandon` → re-raise. `operation_service.get(session,
  id)` landed (2.6's placeholder), and `document_service.create_document` gained
  `document_id=` because the retained payload is named after the row
  (`storage.save_raw_document`), so the id is generated before the file is
  written.
- **Enqueue seam:** `product_service.start_ingestion(session, motorbike) ->
  Operation` is the only way an ingestion starts — `transition` →
  `operation_service.create("ingestion", entity_type="motorbike", entity_id=…)`
  → `enqueue_ingestion(…)`, each committed before the next.
  `product_service.enqueue_ingestion` imports `app.jobs.ingestion` **inside the
  function** (a top-level import is circular and would drag Redis into every
  importer) and is the stub seam: the autouse `recorded_enqueues` fixture in
  `tests/conftest.py` replaces it for every test and records
  `(motorbike_id, operation_id)`. `POST /api/products` therefore answers `201`
  with status **`ingesting`**, and `PATCH status=ingesting` re-enqueues — the
  existing product API tests were updated accordingly (create → `ingesting`,
  "legal transition" now targets `in_review`).
- **Message & failure policy (pinned wording, implemented in the constants of
  `service.py`):** every milestone message carries the warnings collected so far
  (`"<milestone> — <w1>; <w2>"`), a warned success ends as
  `"Completed with warnings: …"` at 100 %, and `operation_service` truncation at
  512 chars is accepted. Zero stored documents → `abandon` with
  `"No usable source documents could be ingested. …"`, **except** when a
  network reason caused it (`wikipedia` `search_failed`/`article_fetch_failed`,
  `fetch` `timeout`/`network_error`) → `TransientJobError`, which deliberately
  leaves the operation `running` and the bike `ingesting` for the retry.
  Deliberate omission: exhausted retries are not reaped in Phase 2 (no
  `ingesting → ingesting` transition exists), so a permanently unreachable
  network leaves a row stuck in `ingesting` until an operator intervenes.
- **Fresh-run semantics:** `_discard_previous_run` deletes the previous
  `source_documents` and `motorbike_images` **rows and their files** (raw
  payloads, original, all three variants) before the first new document, so a
  retry never mixes two runs and `motorbike_images` keeps ≤1 row per model. No
  event announces the deletion (there is no `documentId` to name) — the new rows
  emit `document.updated` each. `app ingest run "<name>"` is create-or-find by
  slug + `start_ingestion` inside `broker.startup()/shutdown()`; it has no test
  file (same precedent as `probe`/`fetch-image`) and was verified live.

### Step 2.17 (spec extraction)

- **`app/llm/extraction.py` is the whole LLM half:** `ExtractedSpec` mirrors
  `SPEC_FIELDS` 1:1 (all optional, `extra="ignore"` so an invented key costs
  nothing), `to_spec_values(extracted_at=…) -> dict` **is** the full-object
  mapping for `upsert_draft_spec` (enums unwrapped, `extra` `None` → `{}`), plus
  `filled_fields()`, `ExtractionDocument(title, source_type, markdown, url=None)`,
  `render_extraction_prompt(name, documents)`, `build_extraction_chain(model=None)`
  (`with_structured_output(…, method="json_schema")`, `strict` deliberately not
  passed — the open `extra`/`source_hints` objects would be illegal in strict
  mode; `ExtractedSpec.model_json_schema` is overridden to list **every**
  property in `required`, which the providers demand even without `strict` —
  see the live-fix bullet below) and `await extract_spec(name, documents,
  model=None)`. Every field has a
  `BeforeValidator`: units normalized from the number's *adjacent* unit only
  ("72 kW (98 hp)" is kW; hp 0.7457 vs PS 0.7355), values outside a
  motorcycle-wide plausibility window in `_QUANTITIES` → `None`, vocabulary
  outside `SPEC_CATEGORIES`/`PRICE_BANDS` → `None`, foreign-currency price →
  `None`, `abs="optional"` → `None`, model-supplied `extracted_at` always
  discarded, `a2_eligible` passed through untouched (2.1 derives it). Phase 3 can
  therefore assume verified specs are plausible, never that they are complete.
- **`spec_extraction_service.extract_draft_spec(session, motorbike, *, model=None)
  -> ExtractionResult | ExtractionFailure`** never raises: `ExtractionFailure
  (reason ∈ no_documents | missing_api_key | model_error, warning-ready `detail`,
  already logged once)` — the adapter convention from 2.10/2.12; `MissingApiKeyError`
  is its own deterministic reason and everything else (`except Exception` around
  the one `await`) is `model_error`. `assemble_documents(documents, *,
  max_input_chars=None)` is the pinned budget: stable sort putting `wikipedia`
  first, each document head-truncated to `DOCUMENT_MAX_CHARS = 12_000`, the one
  that straddles the cap truncated to the remainder, the rest dropped; new config
  `EXTRACTION_MAX_INPUT_CHARS=60000`. Writes go through `upsert_draft_spec` only —
  draft replaced, `verified` never touched (verified against the real DB: two runs
  → one draft row, same id).
- **Ingestion:** `EXTRACTION_MILESTONE = (80, "Extracting specifications")` runs
  in `_Run._extraction_stage`, between `_image_stage` and `_complete`; a failure
  is `self._warn(detail)` and nothing else, so the bike still reaches `in_review`
  (2.19's 90 % stage goes between this stage and `_complete`). Test seam: the
  autouse `extracted_specs` fixture in `tests/services/ingestion/conftest.py`
  stubs `app.llm.extraction.extract_spec` for the **whole** ingestion test
  package (same spirit as `recorded_enqueues`), so the extraction *service* runs
  for real in every orchestration test and no test can reach OpenRouter; the
  milestone lists in `test_service.py` now carry `(80, …)`.
- **CLI `app ingest extract-specs <slug> [--model]`** runs the extraction **in
  process** (nothing enqueued — it is the prompt-tuning loop) and prints the full
  frozen field set; unknown slug / typed failure → stderr + exit 1.
  **Live extraction is BLOCKED: `OPENROUTER_API_KEY` is not set** (as in 2.16), so
  no real completion has been made — prompt quality is unproven. What *is* live
  verified: `app ingest run "Suzuki GSR600"` with no keys ends `succeeded` at
  100 % with both warnings ("Web search skipped: TAVILY_API_KEY…" and
  "Specification extraction skipped: OPENROUTER_API_KEY is not configured."),
  bike `in_review`, `error` NULL, no retry.

### Step 2.18 (chunks table & chunking)

- **`app/services/chunking.py` contract 2.19 fills:** `split_markdown(markdown, *,
  chunk_size=None, chunk_overlap=None) -> list[ChunkCandidate(sequence, text,
  heading_path)]` (pure, sizes default to config — the parameters exist for
  tests), `heading_path(metadata) -> str | None`, `await rebuild_document(session,
  document) -> list[Chunk]` (**delete + insert in one transaction, commits**;
  embeddings are therefore reset to NULL by construction) and `await
  rebuild_for_motorbike(session, motorbike_id) -> RebuildSummary(documents,
  chunks)`. Sequences are **per document**, gap-free from 0; whitespace-only
  slices are dropped; `heading_path` is truncated to 512. Nothing here emits an
  event or touches operations — chunking is not a tracked job (2.19's embedding
  pass is).
- **One glue decision inside the pinned splitter chain:**
  `MarkdownHeaderTextSplitter` joins a section's lines with the Markdown hard
  break `"  \n"`, which destroys the `"\n\n"` the `RecursiveCharacterTextSplitter`
  prefers to cut on (and made stored chunk text *longer* than its source).
  `split_markdown` restores `"  \n"` → `"\n\n"` between the two stages, so stored
  text is byte-identical to the document when a section fits in one chunk
  (verified on the real row: 2720 chars in, 2720 out, substring match).
  Header levels honoured: `#`..`####`; `strip_headers` left at its default, so the
  heading line itself lives only in `heading_path`, not in `text`.
- **`chunks` has no timestamps and no relationships** (per the pinned schema);
  `text_tsv` is mapped as a `deferred` `Computed` TSVECTOR column — never write it,
  never select it into Python. `app/db/models/chunk.py` exports
  `EMBEDDING_DIMENSIONS = 1536` (the `vector` column width) — 2.19's startup guard
  compares `settings.embedding_dimensions` against **that constant**. Migration
  `0a65339a924a` (head) was autogenerated and round-trips; `alembic check` is clean,
  so the HNSW/GIN/Computed DDL is fully expressed in the ORM.
- **Live finding that limited `heading_path` when 2.18 landed — since fixed in
  `ingestion/extract.py`, see the follow-up note below:** trafilatura returned
  **zero ATX headings** for Wikipedia REST HTML (verified on `Suzuki_GSX-R750`,
  18 588 chars, 0 headings), so every `wikipedia` chunk had `heading_path = NULL`.
  The column and the composer were correct all along; the corpus had no headings
  to compose from.

### Step 2.18 follow-up (heading extraction fix)

- **Cause:** trafilatura keeps `<h1>`–`<h6>` only when its main-body detection
  recognises an article container. Wikipedia REST HTML puts the content in bare
  `<section>` elements directly under `<body>`, so extraction falls through to
  trafilatura's "wild text" recovery, which collects `p`/`table`/`code`/`quote`
  and **no heading at all** (`include_formatting`, `favor_recall`, `fast` and the
  `xml` output format change nothing — the heads are already gone before the
  serializer runs).
- **Fix (`app/services/ingestion/extract.py`, signature and result types
  unchanged):** after the normal pass, if the Markdown contains no ATX heading,
  `_extract_with_article_container(html)` re-extracts from a `trafilatura.
  load_html` tree whose body children are moved into one synthetic `<article>`
  element, and that result replaces the first one **only** if it has headings and
  is not shorter. So: heading-less pages and pages that already extract with
  headings are untouched, boilerplate pruning still runs inside the container
  (proved on a nav/cookie/footer fixture), GFM tables survive, and
  `ExtractFailureReason.EMPTY` still comes back for a page with no main text.
  `normalize()` now also accepts `None` (trafilatura's "nothing extracted").
- **Live proof:** `Suzuki_GSX-R750` REST HTML now extracts 21 185 chars with 33
  headings (`##`/`###` at the source's own levels); a throwaway `app ingest run`
  of that model chunked into 32 chunks, **31 with `heading_path`** (e.g. `SRAD >
  GSX-R750 K1 2001`; only the pre-first-heading infobox chunk is NULL, by
  design). Fixtures for the two shapes live in
  `tests/services/ingestion/fixtures/wikipedia_rest_gsr600.html` (Parsoid shape,
  reproduces the old zero-heading behaviour without the fix) and
  `sectioned_review.html` (rescue must not re-import boilerplate).
- **Consequence for 2.19+ / Phase 3:** documents ingested *before* this fix keep
  their heading-less `content_markdown` — `heading_path` only appears after a
  re-ingest (re-chunking alone cannot invent headings, it reads the stored
  Markdown).

### Step 2.19 (embeddings & re-embed CLI)

- **`app/llm/embeddings.py`:** `get_embeddings(model=None) -> OpenAIEmbeddings`
  exactly as pinned (`base_url=OPENROUTER_API_BASE` =
  `openrouter.SERVERS[SERVER_PRODUCTION]` = `https://openrouter.ai/api/v1`,
  `check_embedding_ctx_length=False`, no `dimensions` parameter), empty key →
  `models.MissingApiKeyError`. The HTTPX fallback was **not** needed — the
  wrapper constructs and wires correctly on the pinned versions. Dependency
  `langchain-openai~=1.0` (resolved 1.6.0, pulls `openai`, `tiktoken`, `jiter`,
  `tqdm`); chat still goes through `ChatOpenRouter` only.
  `app llm embeddings-smoke` now reads `EMBEDDING_MODEL`/`EMBEDDING_DIMENSIONS`
  from config (the 2.16 module constants are deleted) and stays a thin HTTPX
  call on purpose — it must not depend on the wrapper it diagnoses.
- **`embedding_service` contract (Phase 3 retrieval builds on this):**
  `require_matching_dimensions()` (guard), `column_dimensions()` (reads
  `Chunk.__table__.c.embedding.type.dim` — the mapped column, which *is*
  `chunk.EMBEDDING_DIMENSIONS`; no DB round trip), `count_documents(session)`,
  `embed_chunks(session, chunks, *, embeddings=None, model=None) -> int`
  (batches `BATCH_SIZE=64`, **one commit per batch**, writes
  `embedding`/`embedding_model`/`embedding_dimensions` per row) and
  `rebuild_motorbike(session, motorbike_id, *, model=None, on_document=None) ->
  EmbeddingResult | EmbeddingFailure(reason ∈ missing_api_key|model_error,
  warning-ready `detail`, already logged once, plus `documents`/`chunks`)`.
  `REBUILD_OPERATION_TYPE = "embeddings.rebuild"` lives here. Every vector is
  measured against `settings.embedding_dimensions` **before** the write
  (`UnexpectedVectorSizeError`, nothing stored). One transient embeddings call
  is retried in-process (`TRANSIENT_ATTEMPTS=3`,
  `TRANSIENT_RETRY_DELAY_SECONDS=2.0`, delay×attempt) and *then* degrades to the
  typed failure — deliberately **not** `TransientJobError`, because retrying the
  ingestion job would re-fetch every source over a gateway hiccup.
- **Two deliberate asymmetries.** (1) `rebuild_motorbike` always finishes
  chunking even when the gateway/key is unusable (chunks are cheap, correct
  without a gateway and rewritten wholesale anyway) — so "chunked, unembedded"
  is a normal state and retrieval must keep filtering on non-null `embedding`.
  (2) The same missing key is a **warning** in the ingestion 90 % stage
  (`EMBEDDING_MILESTONE = (90, "Generating embeddings")`, bike still reaches
  `in_review`, `error` NULL) and a **failed operation** in `embeddings.rebuild`
  (there is nothing else that job could accomplish). `DimensionMismatchError` is
  the only embedding failure that escapes both as an exception: it aborts before
  the first row is touched and its message names the files + the
  `alembic revision --autogenerate` / `alembic upgrade head` sequence.
- **`embeddings.rebuild(operation_id)`** (`app/jobs/embeddings.py`, added to
  `app-worker`'s module list): ids only, own session, `operation_service`
  lifecycle; progress = **documents processed catalogue-wide**
  (`count_documents` first, then `min(n*100//total, 99)` with
  `"Generating embeddings (n/total)"`; `0` = `"Rebuilding the knowledge base"`,
  empty catalogue → succeeded with `EMPTY_MESSAGE`), stops at the first typed
  failure. `app embeddings rebuild` creates the (entity-less) operation row,
  commits, then `.kiq(operation_id)` — the guard is **only** in the job, so the
  CLI always prints an operation id to follow. No CLI test file (precedent of
  `app ingest run`/`probe`/`fetch-image`: DB-touching commands are verified
  live). Job tests live in the new `backend/tests/jobs/` package, whose
  `WorkerSession(FakeAsyncSession)` adds the no-op `rollback` a worker needs.
- **Live embedding verification is BLOCKED — `OPENROUTER_API_KEY` is not set**
  (as in 2.16/2.17): no vector has ever been produced, so batch behaviour
  against the real route and the 1536-dimension assertion remain unproven. What
  *is* live verified with no key: `app ingest run "Yamaha MT-07"` → `succeeded`
  at 100 % with **three** warnings (search, extraction, embeddings), bike
  `in_review`, `error` NULL, 5 chunks written with NULL embeddings; and
  `app embeddings rebuild` → operation `failed`, progress 50,
  `error = "Embedding skipped: OPENROUTER_API_KEY is not configured."`. The
  throwaway model, its files and both operation rows were deleted afterwards.

### Step 2.20 (review wired live, S2)

- **The 2.13 stub contract survived untouched** — no review component or route
  changed. `useProductReview.ts` now re-exports the same five hooks and types,
  with the hand-written types replaced by generated ones (`SourceType`/
  `ImageStatus` = the schema enums, `SourceDocument` = `{id} &
  DocumentAttributes`, `ProductImage` = `{id} & ProductImageAttributes`).
  `useProduct` throws **`ProductError`** (imported from `useProducts.ts`, so the
  route's `instanceof` 404 branch works); the mapping helper is copied inline
  rather than exported from `useProducts.ts`, like the page walk in 2.15.
  `SaveDraftSpecError.validationFields` is filled from the last segment of each
  FastAPI 422 `loc` (`["body","data","attributes","draftSpec","powerKw"]` →
  `powerKw`); a JSON:API error document has no `loc`, so domain failures map to
  the form's general Alert.
- **`useSaveDraftSpec` reads the last-fetched draft from the query cache**
  (`queryClient.getQueryData(queryKeys.products.detail(id))`) and PATCHes
  `{...allNullSpec, ...cached.draftSpec, ...formValues}` — all 16 frozen fields
  always travel, so the full-object replace never resets a field the form does
  not show (proved live: draft was NULL, saving created the row = the upsert
  path). Per 2.9 both list endpoints are unpaginated, so `useProductDocuments` /
  `useProductImage` send **no `page[…]` parameters** and the 2.15 page-walk loop
  is deliberately *not* repeated; `useProductImage` picks the newest row by
  `createdAt` rather than by position. `useRejectImage` invalidates
  `["products"]` + `["operations"]` + `["productImages"]` (ui-spec §1 blanket
  rule; the image PATCH announces `product.updated` server-side).
- **Known dev-only gap (not fixed — would have meant improvising):** image
  variant URLs are the API's server-relative `/media/...` paths and are passed
  through verbatim, so in the cross-origin dev setup (Vite :5173 → API :8000)
  the three previews resolve against Vite, which answers the SPA fallback
  `index.html` and the `<img>` renders blank (`naturalWidth 0`); same-origin
  production is unaffected. One-line fix if wanted: prefix `variants.*` with
  `import.meta.env.VITE_API_URL` in the hook. `AdminModelReviewRoute.test.tsx`
  now serves `/api/documents` + `/api/product-images` fixtures from its
  `stubFetch` API (component sources unchanged), and `useProductReview.test.ts`
  covers ordering, newest-image, merge-before-PATCH, 422 `loc` and invalidations.

### Live fix: 2.17 spec extraction through OpenRouter (key now set)

- **Root cause of the 400:** OpenAI *and* Azure reject a `json_schema` response
  format whose `required` does not name every key in `properties` — even when
  `strict` is not passed (`invalid_json_schema`: "'required' is required to be
  supplied and to be an array including every key in properties"). **Fix:
  `ExtractedSpec.model_json_schema()` is overridden to set `required = list
  (properties)`**; optionality stays expressed as the `null` union Pydantic
  already emits for `T | None`. The pinned
  `with_structured_output(ExtractedSpec, method="json_schema")` and the
  Pydantic-parsed chain output are therefore **unchanged** — no amendment to
  the method pin was needed, and `method="function_calling"` was *not* adopted.
- **`additionalProperties: false` is deliberately NOT added** — a non-strict
  `json_schema` format is accepted without it, so the open-ended
  `extra`/`source_hints` dicts stay legal. Verified live on both upstream
  providers by pinning `openrouter_provider={"order": ["openai"|"azure"],
  "allow_fallbacks": False}`: patched-`required` json_schema succeeded on both
  (`function_calling` also succeeded on both — the fallback if a future
  provider demands the closed schema).
- **Live evidence (`CHAT_MODEL=openai/gpt-4.1-mini`):** `app ingest
  extract-specs suzuki-gsr600` → 10 fields, `category=naked engine_cc=599
  cylinders=4 power_kw=71.5 torque_nm=65.0 seat_height_mm=785
  tank_capacity_l=16.5 top_speed_kmh=250` + 12–14 `extra` entries + per-field
  `source_hints`; run twice → still exactly one `draft` row (same id, only
  `extracted_at` moved). Full worker path re-proved on a throwaway "Honda
  CB500F" (worker recreated): operation `succeeded` at 100 % with only the
  Tavily warning, draft `471 cc / 35.0 kW / 43.0 Nm / 785 mm / ABS true`, 11/11
  chunks embedded (1536 dims) — bike, files and operation deleted afterwards.

### Follow-up: second search provider (`SEARCH_PROVIDER=openrouter`)

- **`config.SearchProviderName = Literal["tavily", "openrouter"]`**, no new
  settings: `OpenRouterSearchProvider` reuses `OPENROUTER_API_KEY` +
  `CHAT_MODEL`. `get_search_provider()` is still the only name→class mapping
  (`"openrouter"` → `OpenRouterSearchProvider()`, else Tavily). Both providers
  keep the identical `search.py` contract: same `QUERY_TEMPLATES` and labelling,
  `RESULTS_PER_TEMPLATE = 2` per query, dedupe by URL, `INGESTION_MAX_WEB_DOCUMENTS`
  cap that also stops later queries, politeness gate on the API host, and warnings
  instead of exceptions (missing key → `"Web search skipped: OPENROUTER_API_KEY is
  not configured."`, a failed query → `f"Web search for {query} failed."`).
- **Deliberately raw httpx, not `app.llm.models.get_chat_model`:** `POST
  OPENROUTER_SEARCH_URL` (`…/api/v1/chat/completions`) with `plugins:
  [{"id": "web", "max_results": RESULTS_PER_TEMPLATE}]`, the model from
  `settings.chat_model`, one user message, and `Authorization` +
  `HTTP-Referer`/`X-Title` from the existing `APP_URL`/`APP_TITLE` constants —
  this module needs an injectable client and the gate, and the LLM is only the
  vehicle for the web plugin, not a reasoning step.
- **Citation-parsing contract:** candidates come **only** from
  `choices[0].message.annotations` entries with `type == "url_citation"` and a
  non-empty string `url_citation.url` (assistant prose is never used); every level
  is isinstance-checked, malformed shapes are skipped silently. OpenRouter appends
  `utm_source=openai` to cited URLs — **only that parameter is stripped**, all other
  query parameters survive, because the URL is provenance and the dedupe key
  downstream (dedupe therefore happens on the cleaned URL).
- **`SEARCH_PROVIDER=tavily` is pinned in `tests/conftest.py::_settings_environment`**
  alongside `DATABASE_URL`/`REDIS_URL`/`ENVIRONMENT`/`LOG_LEVEL`: the root `.env`
  (which `Settings` falls back to, and which compose passes to `app-cli` via
  `env_file`) may legitimately select `openrouter`, so no test may depend on it.
  A test that wants the other provider uses `settings_override(SEARCH_PROVIDER=…)`
  explicitly — the same rule applies to any future provider-selecting setting.
