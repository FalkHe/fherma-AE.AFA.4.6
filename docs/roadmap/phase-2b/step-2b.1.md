---
phase: 2b
step: "2b.1"
title: Manufacturers table, migration & derived products attribute
summary: New manufacturers table (ULID PK, unique slug, description/logo_path NULL), motorbikes.manufacturer_id FK replacing the dropped legacy string column, manufacturer_service, and the products API rendering manufacturer as the derived related name — wire shape unchanged.
effort: 4
dependencies: []
agent: backend-dev
track: backend
---

# Step 2b.1 — Manufacturers table, migration & derived products attribute

**Effort: 4** — the schema refactor lands whole and atomic on purpose:
dropping the legacy column breaks `_resource(...)` unless the derived
attribute lands in the same step.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — the whole file is the pinned
contract (*DB schema*, *Services*, *JSON:API resources*, *Owner decisions*).
[`../phase-2/shared-knowledge.md`](../phase-2/shared-knowledge.md) — *DB
schema* (conventions, slugify), *JSON:API conventions*, *Landed decisions*
(2.1 service/commit contract). `docs/architecture.md`, `docs/backend-stack.md`.
Zero deviations; stop and report if one seems necessary.

## Files

- Create `backend/app/db/models/manufacturer.py`; modify
  `backend/app/db/models/__init__.py`
- Modify `backend/app/db/models/motorbike.py` (drop the `manufacturer`
  column; `MANUFACTURER_LENGTH` moves to the new module or is imported
  from it)
- Create `backend/alembic/versions/<new>_add_manufacturers_table.py`
  (revision off head `0a65339a924a`)
- Create `backend/app/services/manufacturer_service.py`
  (`normalize_name`, `get_or_create`, `get_by_ids`, `list_manufacturers`);
  modify `backend/app/services/product_service.py`
  (`assign_manufacturer`)
- Modify `backend/app/api/endpoints/products.py` (`_resource` gains a
  `manufacturers` mapping; one `get_by_ids` call per request — list and
  detail); `backend/app/api/schemas/products.py` docstring only (shape
  unchanged)
- Create `backend/tests/services/test_manufacturer_service.py`; modify
  `backend/tests/api/test_products.py` (fixtures that set `manufacturer`
  now go through the new table)
- Modify `docs/roadmap/phase-3/shared-knowledge.md` (*DB schema* head chain)
  and `docs/roadmap/phase-3/step-3.1.md`: replace the Phase-2b placeholder
  with the concrete new revision id — the migration author owns these edits
- Modify `docs/roadmap/phase-2/shared-knowledge.md`: dated supersession
  notes at the `motorbikes` schema row (`manufacturer`) and the `products`
  attribute list — "derived from the `manufacturers` table since Phase 2b,
  see `../phase-2b/shared-knowledge.md`" (same style as existing superseded
  notes)

## Implementation outline

- Table, FK, index, backfill and legacy-column drop exactly as pinned in
  shared-knowledge *DB schema* — including the lossless downgrade and the
  in-migration ULID generation + inlined slugify.
- Service semantics as pinned in *Services*: get-or-create keyed on slug,
  `IntegrityError` → rollback + re-select; public functions commit;
  `assign_manufacturer` announces `product.updated`.
- `manufacturer` in the products payload becomes the related row's `name`
  (`null` when unassigned) — attribute set otherwise verbatim.

## Out of scope

- Extraction and CLI (2b.2), `/api/manufacturers` endpoints (2b.3), any
  admin UI, any frontend change.

## Verification (dev — infrastructure)

- `make backend-test` and `make lint` green.
- Migration round-trip against the dev DB **with a pre-seeded legacy
  string** (seed one motorbike's `manufacturer` before upgrading):
  `alembic upgrade head` → manufacturers row + FK exist → `alembic
  downgrade -1` → string restored → `upgrade head`. `\d motorbikes` /
  `\d manufacturers` shape check.
- `make generate-api` → `git diff --stat frontend/src/api/schema.d.ts`
  is empty.
- Existing suite still green (products API wire shape unchanged).

**On finish:** append the new migration revision id and any cross-step
decisions to `shared-knowledge.md` → *Landed decisions*, and make the
phase-3 head-pointer edits listed under Files.
