---
phase: 4
step: "4.8"
title: Model detail page on stubs
summary: CatalogueModelRoute at /catalogue/:motorbikeId — image gallery with fallback, the 13 verified spec fields grouped per ui-spec, article prose via react-markdown (raw HTML off), a visible Sources block, and the 404 state — on stub hooks, zero backend code.
effort: 3
dependencies: ["4.6", "4.7"]
---

# Step 4.8 — Model detail page on stubs

**Effort: 3** — one read-only page with rich content sections, reusing the
landed spec-field module and markdown conventions.

Binding contracts: `docs/roadmap/stage-01/phase-4/ui-spec.md` and
`docs/roadmap/stage-01/phase-4/shared-knowledge.md`. Agent: **frontend-dev**. Needs
**zero backend code**. Zero deviations — a deviation is a stop-and-report.

## Outline

- `frontend/src/hooks/useCatalogueModel.ts` — **stub** (pinned exports so
  4.9 deletes it wholesale): `useCatalogueModel(motorbikeId)` + types
  `CatalogueModelDetail`, `CatalogueImage`, `ModelSource`,
  `CatalogueError` (`status` + `code`, the `ProductError` shape). Fixture
  requirements are **binding** in ui-spec §8 (fully-populated model incl.
  2 images + GFM/`<script>` article + de-dup source, sparse model, 404
  id).
- `frontend/src/routes/CatalogueModelRoute.tsx` at
  `/catalogue/:motorbikeId` (route table in `App.tsx`): breadcrumbs,
  header + chips row per ui-spec §4.1;
  `frontend/src/components/ModelImageGallery.tsx` (§4.2 — thumbnails when
  >1, attribution caption, image-less fallback, `objectFit: "contain"`);
  `frontend/src/components/ModelSpecTable.tsx` (§4.3 — the 13 frozen
  fields in the four pinned groups via `components/specFields.ts`, **null
  fields render no row, all-null groups render no header**, `msrpEur` via
  `Intl.NumberFormat` EUR).
- Article block (§4.4): nullable `article` markdown via react-markdown +
  remark-gfm, **raw HTML off** (retrieved web content — same rule as chat
  bubbles); heading `catalogue.detail.aboutHeading`; absent when null.
- `frontend/src/components/ModelSources.tsx` (§4.5, grading-critical,
  **always expanded**): title + external URL (`target="_blank"
  rel="noopener noreferrer"`), hostname secondary, URL-less rows as plain
  text, de-dup by URL, empty-sources note.
- States per ui-spec §4.6: skeleton page (no layout jump), error with
  retry, **404 for unknown/unapproved id** (deep-link renders the
  not-found state after guard/backoff, the landed admin-review
  precedent), no-image / all-null-specs / no-article variants.
- i18n `catalogue.detail.*` additions per ui-spec §9.

## Verification

- `make frontend-test` + lint + typecheck green; tests: grouped table
  renders only non-null values with units, GFM table + headings render in
  the article fixture and raw HTML stays inert, sources links carry
  `rel="noopener"`, 404 fixture shows the not-found state, image-less
  fixture shows the fallback.

## Risks / notes

- The card→detail link already works from 4.7's grid; the
  recommendation-card link is **not** this step (4.9).
- Append decisions (`### Step 4.8`) to `shared-knowledge.md`.
