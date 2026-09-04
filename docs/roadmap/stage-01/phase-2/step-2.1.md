---
phase: 2
step: "2.1"
title: Catalogue domain models & services
summary: The four catalogue tables (motorbikes, source_documents, motorbike_specs, motorbike_images) in one migration, plus product/document services owning the full status-transition matrix and the approval promotion (draft→verified spec, pending→approved image).
effort: 4
dependencies: ["1.1"]
agent: backend-dev
track: backend
---

# Step 2.1 — Catalogue domain models & services

**Effort: 4** — four interrelated tables + one migration + the two services
every later backend step builds on.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — the *DB schema* section is the
spec, column by column: table shapes, enum names/values, index/constraint
names, the **legal transition matrix**, the pinned `rejected` semantics, and
the **frozen core spec column set**. Phase-3 tools filter on exactly those
spec columns — zero deviations; if a deviation seems necessary, stop and
report. Also apply the Phase-1 landed decisions
(`../phase-1/shared-knowledge.md` → *Landed decisions*): module-level service
functions taking `AsyncSession` first, `values_callable` enums, no ORM
relationships.

## Files

- Create `backend/app/db/models/motorbike.py`, `source_document.py`,
  `motorbike_spec.py`, `motorbike_image.py`
- Create one Alembic version (all four tables)
- Create `backend/app/services/product_service.py`,
  `backend/app/services/document_service.py`
- Create `backend/tests/services/test_product_service.py`,
  `test_document_service.py`
- Modify `backend/app/db/models/__init__.py`

## Implementation outline

- Models exactly per the pinned schema (ULID mixin, TIMESTAMPTZ, naming
  convention, native enums with `values_callable`).
- `product_service`: `create_backlog(name)` (slugify per the pinned rule;
  duplicate slug raises a domain error the API maps to 409),
  `transition(motorbike, new_status)` enforcing the matrix (illegal → domain
  error mapped to 422 `invalid-transition`), spec upsert
  (`upsert_draft_spec`), and the **approval side effects in one
  transaction**: draft spec copied/upserted to `verified`, all `pending`
  images → `approved`. `a2_eligible` derived on spec write **only when the
  incoming value is null** and power + weight are known (explicit admin
  values win; formula pinned).
- `document_service`: create source-document rows; list by motorbike
  (Wikipedia first, then `created_at`).
- Services own transactions (commit in the service). No enqueue/NOTIFY here —
  those side effects arrive in 2.6/2.14.

## Out of scope

- Any HTTP endpoint (2.3), operations/NOTIFY (2.6), ingestion enqueue (2.14),
  chunks table (2.18).

## Verification (dev owns infrastructure claims)

- `make backend-test` green; `alembic upgrade head` + `downgrade -1`
  round-trip clean.
- Service tests prove: every legal transition passes, every illegal one
  raises, approval promotes draft→verified and flips pending images in one
  transaction, `rejected` retains draft/documents/images, `a2_eligible`
  derivation boundary (35.0 kW, ratio exactly 0.2).

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
