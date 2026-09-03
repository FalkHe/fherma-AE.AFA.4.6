---
phase: 2
step: "2.14"
title: Ingestion orchestration job
summary: The ingestion.run Taskiq task + orchestrating service — backlog→ingesting enqueue on create/retry, Wikipedia-first then search-fetch-extract into source_documents, the image stage, pinned operation progress milestones, success→in_review / failure→backlog — plus `app ingest run`.
effort: 4
dependencies: ["2.3", "2.6", "2.11", "2.12"]
agent: backend-dev
track: backend
---

# Step 2.14 — Ingestion orchestration job

**Effort: 4** — the step that composes everything: job machinery (2.5/2.6),
adapters (2.11), fetch/extract (2.10), images (2.12), catalogue writes (2.1).

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *Operation lifecycle &
progress messages* (the milestone table is a contract — the UI renders these
verbatim), *Ingestion decisions* (source order, caps, partial-failure rule),
*Taskiq wiring* (retry policy, commit-then-enqueue), *DB schema* (transition
matrix: success → `in_review`, failure → `backlog`). Zero deviations; stop
and report if one seems necessary.

## Files

- Create `backend/app/jobs/ingestion.py` (`ingestion.run` task)
- Create `backend/app/services/ingestion/service.py` (orchestration)
- Create orchestrator tests (mocked adapters) under
  `backend/tests/services/ingestion/`
- Modify `backend/app/services/product_service.py` (enqueue-on-transition:
  create-auto-start and PATCH→`ingesting` both enqueue **after commit**),
  `backend/app/api/endpoints/products.py` (wire the side effect),
  `backend/app/cli/ingest.py` (`run "<name>"` command),
  `compose.yaml` (worker module list + `app.jobs.ingestion`)

## Implementation outline

- Orchestration per pinned order, advancing the operation at each milestone:
  Wikipedia lookup (5 %) → web search (15 %) → fetch/extract each candidate
  (20–60 %, `Fetching sources (n/m)`) → image stage (65 %) →
  *(2.17 adds extraction at 80 %, 2.19 embeddings at 90 %)* → succeed (100 %),
  transition `ingesting → in_review`.
- Partial source failures append a warning to `message`, never fail the job;
  **zero usable documents = deterministic failure** — operation `failed`
  with `error`, motorbike back to `backlog`. Transient errors raise
  `TransientJobError` (2.5 retry policy).
- Re-ingestion (retry) replaces prior source documents/image for the bike
  (fresh run semantics — pinned `rejected → ingesting` path).
- Emit the pinned events: `document.updated` on every source-document row
  creation/replacement; status flips emit `product.updated` automatically by
  going through `product_service.transition` (2.6) — never bypass it.
- `POST /api/products` now: create backlog row → commit → transition to
  `ingesting` → commit → `.kiq()`. Same for PATCH→`ingesting`.
- `app ingest run "<name>"`: create-or-find by slug, enqueue, print the
  operation id.

## Verification

- `make backend-test` green (orchestrator fully tested with mocked
  adapters: milestone sequence, partial-failure warning, zero-document
  failure path, replace-on-retry).
- Manual (worker running, real network): `app ingest run "Suzuki GSR 600"` →
  ≥3 `source_documents` (Wikipedia first), a pending image row, status
  `in_review`, operation `succeeded` with the pinned messages;
  `GET /api/operations?filter[entityId]=<bike-id>` reflects the end state
  (there is no operations detail endpoint — list + filters only).

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
