---
phase: 2
step: "2.3"
title: JSON:API layer & /api/products
summary: The small internal JSON:API layer (document envelope, page-number pagination, filters, error objects — includes deferred) plus the products resource — list/get, POST create-backlog, PATCH status-transition/draftSpec — admin- and CSRF-guarded.
effort: 4
dependencies: ["2.1", "1.3"]
agent: backend-dev
track: backend
---

# Step 2.3 — JSON:API layer & `/api/products`

**Effort: 4** — the project's first JSON:API resource; the layer built here
is reused verbatim by 2.6 and 2.9. **This step's OpenAPI output is consumed
by frontend sync point S1 (step 2.15) — the pinned contract is the spec, not
a suggestion.**

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *JSON:API conventions* (media
type, pagination, error objects, resource shapes) and *DB schema* (transition
matrix; spec camelCase mapping). `docs/architecture.md` → *API Design*.
Phase-1 `deps.py` provides `current_admin` and `csrf_protect` — use them,
don't reinvent. Zero deviations; stop and report if one seems necessary.

## Files

- Create `backend/app/api/jsonapi.py` (envelope/pagination/error helpers —
  small and generic, no third-party framework)
- Create `backend/app/api/schemas/products.py`
- Create `backend/app/api/endpoints/products.py`
- Create `backend/tests/api/test_products.py`
- Modify `backend/app/main.py`, `backend/app/api/endpoints/__init__.py`,
  `backend/app/api/schemas/__init__.py`

## Implementation outline

- Resource per the pinned contract: attributes `name, slug, manufacturer,
  modelName, yearFrom, yearTo, status, draftSpec, verifiedSpec, createdAt,
  updatedAt`. **No relationships/includes in Phase 2** — the jsonapi layer
  covers envelope, pagination, filters and error objects only; include
  machinery is deferred until a resource needs it.
- `GET /api/products` (`filter[status]` comma-separated, pagination, default
  sort `-createdAt`), `GET /api/products/{id}`.
- `POST /api/products` `{name}` → 201 backlog row; duplicate slug → 409
  `duplicate-model`. **No enqueue yet** — the auto-start side effect is 2.14's.
- `PATCH /api/products/{id}`: `status` via `product_service.transition`
  (illegal → 422 `invalid-transition`), `draftSpec` full-object replace
  (upsert). Rejects `verifiedSpec` in the payload.
- All routes `Depends(current_admin)`; writes + `Depends(csrf_protect)`.
  Error responses use the pinned `errors[]` shape with stable `code`s.

## Out of scope

- Documents/images endpoints (2.9), operations endpoint (2.6), enqueue-on-
  create (2.14).

## Verification

- `make backend-test` green. As admin via TestClient: POST →
  201 JSON:API document; `GET ?filter[status]=backlog` returns it; PATCH
  backlog→approved → 422 `invalid-transition`; PATCH draftSpec persists and
  echoes camelCase; non-admin → 403; missing CSRF header on write → 403.

**On finish:** append cross-step decisions (e.g. jsonapi.py helper API) to
`shared-knowledge.md` → *Landed decisions*.
