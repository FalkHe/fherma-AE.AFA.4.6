---
phase: 4
step: "4.4"
title: /api/catalogue-models endpoints + manufacturers read relax
summary: The customer-facing read-only JSON:API resource (slim filtered/sorted list, self-contained detail with specs/article/sources/images, 404 for non-approved) and the manufacturers router relaxed from current_admin to current_user. Freezes the Phase-4 OpenAPI surface (opens S1).
effort: 3
dependencies: ["4.3"]
---

# Step 4.4 — `/api/catalogue-models` endpoints + manufacturers read relax

**Effort: 3** — two read routes composing the 4.3 service reads plus one
router-dependency change, against the fully pinned wire contract.

Binding contract: `docs/roadmap/phase-4/shared-knowledge.md` (read fully —
the resource tables there are the wire truth; this file only sequences the
work). JSON:API mechanics: reuse `app/api/jsonapi.py` exactly as landed in
2.3 (see `docs/roadmap/phase-2/shared-knowledge.md` Landed decisions 2.3 and
2.9). Agent: **backend-dev**. Zero deviations — a deviation is a
stop-and-report.

## Outline

- `backend/app/api/schemas/catalogue_models.py`:
  `CatalogueModelSummaryAttributes` (the 11 pinned slim attributes) and
  `CatalogueModelAttributes` (detail: `name`, `manufacturer`, `specs` —
  exactly the 13 frozen camelCase fields, nulls explicit — `article`,
  `sources[]`, `images[]`; nothing more — the pinned attribute set is
  deliberately minimal). No request models
  (read-only resource; the 2b.3 `SpecAttributes` precedent).
- `backend/app/api/endpoints/catalogue_models.py`: router
  `Depends(current_user)` (no `csrf_protect` — no writes), registered
  alphabetically in `backend/app/main.py`.
- **List**: parse the pinned `filter[…]` params into the 3.8 `SpecFilters`
  (vocabulary members → 400 `invalid-filter` on unknown; typed
  numeric/bool params → default 422 on junk; `filter[manufacturer]` =
  ULIDs, unknown id matches nothing), `sort` as
  `Literal["name","-name","msrpEur","-msrpEur"]` default `name`, standard
  `page[number]`/`page[size]` + `meta.totalCount`. One
  `browse_motorbikes` call + one `manufacturer_service.get_by_ids` + one
  `newest_approved_images` per request — no N+1.
- **Detail**: `get_motorbike` + approved check (anything else → 404
  `not-found`, no existence leak), `get_verified_specs`,
  `get_by_ids`, `document_service.list_for_motorbike` (article = first
  `wikipedia` document's `content_markdown`, else null; sources list per
  pinned shape, never `contentMarkdown`/`rawPath`),
  `list_images(statuses=[APPROVED])` newest first with `variant_urls` +
  `attribution`.
- `backend/app/api/endpoints/manufacturers.py`: router dependency
  `current_admin` → `current_user`. Nothing else changes.
- Error codes: reuse `not-found`, `invalid-filter` only.

## Verification

- Suite + lint green; TestClient tests for filters/sort/404/role scoping.
- Live curl matrix as a **plain user** (stack up, `make up`): list shows
  only approved slim rows; each filter family narrows; `sort=-msrpEur`
  answers 200 with priceless bikes last; detail carries
  specs/article/sources/images; an `in_review` id → 404; plain user still
  403 on `/api/products`; `GET /api/manufacturers` → 200 as user, still
  200 as admin.
- `make generate-api` produces a purely additive `schema.d.ts` diff
  (products types byte-identical). **This opens S1** — commit before 4.9
  starts.

## Risks / notes

- The recommendation snapshots stay untouched — do not "improve" the chat
  code to read the new endpoint.
- Append cross-step decisions (`### Step 4.4`) to `shared-knowledge.md` —
  4.9 builds against the generated types of this surface.
