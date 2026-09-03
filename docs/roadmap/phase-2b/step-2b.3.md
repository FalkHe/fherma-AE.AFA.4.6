---
phase: 2b
step: "2b.3"
title: /api/manufacturers read endpoints
summary: Admin-only read-only JSON:API manufacturers resource — paginated list sorted by name plus detail get — reusing the existing jsonapi layer verbatim; no writes, no filters, no includes.
effort: 2
dependencies: ["2b.1"]
agent: backend-dev
track: backend
---

# Step 2b.3 — `/api/manufacturers` read endpoints

**Effort: 2** — a small read-only resource on the existing jsonapi layer;
the service functions already exist (2b.1). Owner decision 2026-08-27: added
now rather than deferred to Phase 4.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *JSON:API resources* →
`manufacturers` (the pinned contract).
[`../phase-2/shared-knowledge.md`](../phase-2/shared-knowledge.md) —
*JSON:API conventions* and *Landed decisions* → Step 2.3 (jsonapi helper
API). `backend/app/api/endpoints/products.py` is the reference
implementation. Zero deviations; stop and report if one seems necessary.

## Files

- Create `backend/app/api/schemas/manufacturers.py` and
  `backend/app/api/endpoints/manufacturers.py`
- Modify `backend/app/main.py`, `backend/app/api/endpoints/__init__.py`,
  `backend/app/api/schemas/__init__.py`
- Create `backend/tests/api/test_manufacturers.py`

## Implementation outline

- Resource type `manufacturers`, attributes `name, slug, description,
  logoPath, createdAt, updatedAt`. `GET /api/manufacturers` (page-number
  pagination, sorted by `name`, no filters) via
  `manufacturer_service.list_manufacturers`; `GET /api/manufacturers/{id}`
  (404 → code `not-found`). Whole router `Depends(current_admin)` — reads
  included, per the Phase-2 rule. **No POST/PATCH/DELETE** — rows are
  created only by `get_or_create` (extraction/CLI).

## Out of scope

- Writes, filters, includes, customer-facing exposure (Phase-4 step 4.2
  decides catalogue-filter semantics), any frontend consumption.

## Verification (dev — infrastructure)

- `make backend-test` and `make lint` green. Via TestClient: list is sorted
  by name and paginated; detail returns the pinned attributes; unknown id →
  404 `not-found`; non-admin → 403.
- `make generate-api` succeeds; the schema.d.ts diff is purely additive
  (new `manufacturers` paths, no change to products types); `make
  frontend-test` still green.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
