---
phase: 2
step: "2.6"
title: "Operations: model, service, NOTIFY, API"
summary: The operations table + migration, operation_service (create/advance/succeed/fail with commit-then-pg_notify on app_events), the read-only /api/operations resource, and an `app operations demo` CLI that drives a fake operation through its lifecycle.
effort: 3
dependencies: ["2.3", "2.5"]
agent: backend-dev
track: backend
---

# Step 2.6 — Operations: model, service, NOTIFY, API

**Effort: 3** — one table, one service with a strict ordering rule, one
read-only resource on the 2.3 JSON:API layer, one dev CLI.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *DB schema → operations*,
*Operation lifecycle & progress messages*, *SSE / LISTEN-NOTIFY* (channel
name, payload shapes, **commit first, then `pg_notify`**), *JSON:API
conventions → operations*. Zero deviations; stop and report if one seems
necessary.

**Migration-order rule:** this migration lands after 2.1's (single Alembic
head — never parallelize with another migration-bearing step).

## Files

- Create `backend/app/db/models/operation.py` + one Alembic version
- Create `backend/app/services/operation_service.py`
- Create `backend/app/api/schemas/operations.py`,
  `backend/app/api/endpoints/operations.py`
- Create `backend/app/cli/operations.py`
- Create `backend/tests/services/test_operation_service.py`,
  `backend/tests/api/test_operations.py`
- Modify `backend/app/main.py`, `backend/app/db/models/__init__.py`,
  `backend/app/cli/main.py`

## Implementation outline

- `operation_service`: `create(type, entity_type=None, entity_id=None)`
  (status `queued`), `start`, `advance(progress, message)`, `succeed`,
  `fail(error)`. Every state change: **commit, then**
  `pg_notify('app_events', payload)` with the pinned ids-only JSON.
- Wire the pinned `product.updated` emitters now that the NOTIFY helper
  exists: `product_service.transition` (every status change), product
  creation, and the `draftSpec` PATCH all emit after commit — this event is
  what flips the backlog chip live (`ingesting → in_review`).
- `GET /api/operations` read-only per the pinned resource shape (filters
  `entityType`/`entityId`/`status`, default sort `-createdAt`),
  `Depends(current_admin)`.
- `app operations demo [--bike <slug>]`: creates a `demo` operation —
  with `--bike`, linked via `entity_type='motorbike'` / `entity_id` to that
  row (required for the backlog progress cell, which looks operations up by
  entity id) — and walks queued→running→(progress ticks)→succeeded with
  short sleeps. Exists so frontend step 2.15 can prove live progress on a
  real backlog row before real ingestion (2.14) lands.

## Verification

- `make backend-test` green; migration round-trips.
- `app operations demo` then `GET /api/operations` shows the finished row;
  during the run, `psql` `LISTEN app_events;` prints ids-only payloads
  (≤1 KB) on every state change; a products PATCH transition emits
  `product.updated` on the same channel.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
