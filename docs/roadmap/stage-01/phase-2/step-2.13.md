---
phase: 2
step: "2.13"
title: Review screen, UI-only
summary: The model review route per ui-spec — Documents tab (react-markdown + remark-gfm, raw HTML off), Specs tab (RHF + Zod draft-spec form), Image tab (variants, attribution, reject), approve/reject bar with ConfirmDialog — against a pinned useProductReview stub.
effort: 4
dependencies: ["2.2", "2.8"]
agent: frontend-dev
track: frontend
---

# Step 2.13 — Review screen, UI-only

**Effort: 4** — one route, four components, the phase's only RHF+Zod form;
every layout/state decision is already made in the ui-spec.

**Required reading before any code:**
[`ui-spec.md`](ui-spec.md) §2.3 + §6–§11 — binding, component by component
(gates matrix in §6 especially). [`shared-knowledge.md`](shared-knowledge.md)
— *Frontend conventions* (**2.13 stub rule with the exact fixture set**,
hook exports), *DB schema* (price-band/category vocabularies → fill the
`priceBandValues.*`/`categoryValues.*` i18n blocks from them). Zero
deviations; stop and report if one seems necessary.

## Files

- Create `frontend/src/routes/admin/AdminModelReviewRoute.tsx`
- Create `frontend/src/components/ModelDocumentsPanel.tsx`,
  `ModelSpecsPanel.tsx`, `ModelImagePanel.tsx`, `ConfirmDialog.tsx`
- Create `frontend/src/hooks/useProductReview.ts` (STUB)
- Modify `frontend/src/App.tsx` (route `/admin/models/:motorbikeId`),
  `frontend/src/locales/en/translation.json` (§10 review keys + vocab
  values), `frontend/package.json` (+`react-markdown`, `remark-gfm`,
  `react-hook-form`, `zod`, `@hookform/resolvers`)

## Implementation outline

- Stub per the pinned rule (deleted wholesale in 2.20): fixtures include a
  Markdown document with headings **and a GFM table**, a `draftSpec` with
  some nulls, a `pending` image with attribution. `useTransitionProduct`
  comes from the existing 2.8 `useProducts.ts` stub — do not duplicate it.
- Transcribe ui-spec §6 (breadcrumbs, header, action bar, `?tab=` tabs, the
  page-gate matrix incl. the ingesting gate reusing `OperationProgress`),
  §7 (master–detail documents, provenance line, external-link renderer),
  §8 (RHF+Zod form, unit adornments, three-state A2 select, read-only
  `extra` table, verified read-only mode), §9 (image variants, attribution
  block, reject flow).
- Run `make rebuild` after the dependency change (node_modules volume).
- Tests: Zod schema (empty string → null, negative rejected), gate matrix
  per status, unsaved-edits warning in the approve dialog.

## Out of scope

- Real API calls (2.20). Image replacement-by-upload (explicitly deferred).

## Verification

- `pnpm typecheck && pnpm lint && pnpm test` green.
- In the browser against the stub: all three tabs render per spec (GFM table
  visible, raw HTML inert), form dirty/save/reset behavior, approve/reject
  confirm dialogs incl. pending states, every gate status reachable by
  editing the fixture.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
