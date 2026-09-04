---
phase: 2
step: "2.9"
title: Documents & images endpoints
summary: Read-only JSON:API /api/documents (contentMarkdown + provenance, filter[product]) and /api/product-images with admin PATCH status (approve/reject) — variant URLs computed from the pinned deterministic path formula.
effort: 3
dependencies: ["2.1", "2.3", "2.6"]
agent: backend-dev
track: backend
---

# Step 2.9 — Documents & images endpoints

**Effort: 3** — two thin resources on the existing JSON:API layer; the only
logic is the image status matrix and computed variant URLs.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *JSON:API conventions →
documents / product-images* (attribute lists, filters, the image status
transitions) and *DB schema* (deterministic variant path formula). Zero
deviations; stop and report if one seems necessary.

## Files

- Create `backend/app/api/schemas/documents.py`, `images.py`
- Create `backend/app/api/endpoints/documents.py`, `images.py`
- Create `backend/tests/api/test_documents.py`, `test_images.py`
- Modify `backend/app/main.py`, `backend/app/api/endpoints/__init__.py`,
  `backend/app/api/schemas/__init__.py`

## Implementation outline

- `GET /api/documents?filter[product]=<id>` (filter **required** on list;
  400 `missing-filter` without it), ordering Wikipedia first then
  `createdAt`; attributes incl. `contentMarkdown` and full provenance.
- `GET /api/product-images?filter[product]=<id>`; `variants` attribute
  computed as `/media/motorbikes/{motorbike_id}/{image_id}_{variant}.webp`
  for thumb/card/detail — never stored, never read from disk.
- `PATCH /api/product-images/{id}`: `status` only; legal `pending→approved`,
  `pending→rejected`, `approved→rejected`; anything else 422
  `invalid-transition`. Emits `product.updated` NOTIFY (via the 2.6
  service pattern) so the review screen refetches.
- All routes `Depends(current_admin)`; PATCH + `csrf_protect`.

## Verification

- `make backend-test` green. Seeded rows: document list returns Markdown +
  provenance in pinned order; image PATCH pending→rejected → 200; illegal
  transition → 422; missing `filter[product]` → 400; variant URLs match the
  formula exactly.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
