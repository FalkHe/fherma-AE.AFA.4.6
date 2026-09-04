---
phase: 6
step: "6.24"
title: Review identity section and claim-vs-finding, UI-only
summary: The admin identity tab — form, options loading, Zod submit-only validation, save flow with both error surfaces, read-only-when-approved — plus the claim panel with per-field "use the claim" and the contradiction-warning Alert; built entirely on stubs/fixtures, with the D6 boundary proven by a test.
effort: 4
dependencies: []
---

# Step 6.24 — Review identity section and claim-vs-finding, UI-only

**Effort: 4** — two new components, route surgery (fourth tab, dirty-flag
rename, approve-dialog message), one mutation hook, the §1.3 validation
matrix and the §2.3 claim interactions, all with tests — against stubs,
deliberately: this runs during M1, in parallel with the backend schema work.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (D1, D2, D4,
D6, D13), **`docs/roadmap/stage-01/phase-6/ui-spec.md` §0 (file map), §1, §2, §7
(i18n)** and `docs/roadmap/stage-01/phase-6/model-naming-display-spec.md` §6.1, §6.2, §11 —
the truth for every layout, field behaviour, state and copy; this file only
sequences. Agent: **frontend-dev**. Zero deviations — a deviation is a
stop-and-report.

**Environment:** no backend code exists for this step and none is needed;
tests run via `make frontend-test` with the stack down. Backend 6.9–6.13 run
concurrently — do not touch `backend/` and do not wait for it.

## Outline

- `frontend/src/routes/admin/AdminModelReviewRoute.tsx`: add `identity` to
  `TABS` **first in order**, default stays `documents` (`?tab=identity`
  addresses it); rename `hasUnsavedSpecs` → `hasUnsavedChanges`, OR of both
  panels' `onDirtyChange` (ui-spec §0, §1.4); pass the row's latest
  operation into the panel (§2.4); approve dialog passes
  `errorMessage` = `t("admin.review.approveBlockedIdentity")` when
  `transition.error` carries code `incomplete-identity` (§1.6).
- `frontend/src/components/ConfirmDialog.tsx`: optional
  `errorMessage?: string`, absent = today's generic text — zero behaviour
  change at other call sites (§1.6).
- **New `frontend/src/components/ModelIdentityPanel.tsx`** — display-spec
  §6.2 as written (fields, `Autocomplete` behaviours, casing-snap,
  two-level live preview, `onDirtyChange` with stable callback +
  unmount-cleanup, mirroring `ModelSpecsPanel`) plus ui-spec §1.1 (the two
  read-only context rows: `slug` monospace + `slugHint`, `queryName`
  quoted), §1.2 (options loading: field-slot `Skeleton`s, warning `Alert` +
  retry on options failure), §1.3 (Zod, **submit-only**, exact rules and
  keys), §1.4 (one save, `Save identity`/`Discard`, success `Snackbar`),
  §1.5 (409 `duplicate-model` → general `Alert` above the buttons, values
  kept; mappable 422 → `form.setError` per field; else `serverError`),
  §1.7 (approved → read-only table, no form, claim panel collapsed in an
  `Accordion`), §1.8 states. The preview composes levels 1/2 with a
  **panel-local pure helper** using the `common.modelName.*` keys and the
  `queryName` fallback (display-spec §1.3, §11) — see Risks.
- **New `frontend/src/components/ModelClaimPanel.tsx`** — ui-spec §2.2
  (always-expanded `Paper`, warning chip, `raw`/`source` plain text, links
  as `ExternalLink` treatment), §2.3 (per-field claim rows and "use the
  claim": fills the form buffer via `setValue(..., { shouldDirty: true })`,
  never saves; manufacturer button only on a case-insensitive option match;
  years fill both fields per the collapse rule; type codes union up to the
  cap), §2.1 doc comment pinning the component boundary. No suggestion →
  no panel.
- Contradiction warning (§2.4): `Alert severity="warning"` between claim
  panel and form when the succeeded operation's `message` starts with the
  duplicated frontend constant `WARNING_SUMMARY_PREFIX = "Completed with
  warnings: "` (source comment naming
  `backend/app/services/ingestion/service.py:76`); body = message with the
  prefix stripped, verbatim.
- Hooks: **`useSaveIdentity(productId)`** in
  `frontend/src/hooks/useProductReview.ts` — final name and signature,
  `PATCH /api/products/{id}` with the ui-spec §8 API-1 `identity` block,
  error mapping mirroring `useSaveDraftSpec` (`status` + `code` +
  validation field pointers), invalidates `queryKeys.products.detail(id)`
  on success. The generated schema lacks `identity` until 6.20: type the
  body with a local type matching API-1's names exactly and **one
  commented cast**, removed by 6.27. **New
  `frontend/src/hooks/useBuildinglines.ts`** — `useBuildinglines(
  manufacturerId)`, `staleTime: 5 * 60_000`, `enabled` only with a
  manufacturer; fetcher is a plain typed `fetch` against the proposed
  `GET /api/manufacturers/{id}/buildinglines` → `string[]` (the
  `useServerEvents` `VITE_API_URL` precedent), swapped for the generated
  client in 6.27. `frontend/src/queryKeys.ts`: `buildinglines`
  builder (`["buildinglines", manufacturerId]`).
- Local additive typing: the row's new members (`suggestion`, `queryName`,
  `buildingline`, `typeCodes`, `slug` path-shaped) via a local exported
  type in `useProductReview.ts`, **byte-matching ui-spec §8 API-1's
  camelCase names** so 6.27 is a type swap, not a rewrite.
- i18n (`frontend/src/locales/en/translation.json`): ui-spec §7's
  `admin.identity.*` **except the `variants` subtree** (6.25) +
  `admin.review.approveBlockedIdentity`, plus display-spec §9's
  `admin.review.tabs.identity`, `admin.identity.typeCodeA11y` /
  `typeCodesMore` / `typeCodesHint`, `admin.identity.preview.*` and the
  `common.modelName.year*` keys the preview needs.
- Tests — new `frontend/src/components/ModelIdentityPanel.test.tsx` and
  `ModelClaimPanel.test.tsx`, stubbing via the landed
  `frontend/src/test/network.ts` dispatcher (`stubFetch` + `jsonResponse`;
  `stubPendingFetch` for the options-skeleton state) and fixtures shaped
  exactly per §8 API-1: the §1.8 and §2.4 **Test hooks** lists, item by
  item. **The D6 boundary is a test, not a comment** (§2.1 "enforced
  twice"): a compile-time assertion (`// @ts-expect-error`) that
  `suggestion` is not a member of the customer `CatalogueModelDetail`
  type, plus the claim-panel importer pin asserted in its test.

## Verification

- `pnpm lint`, `pnpm typecheck`, `make frontend-test` green (all §1.8/§2.4
  test hooks covered).
- Dev-server smoke (`make up`): `/admin/models/:id?tab=identity` on a real
  row renders without crash against today's pre-6.20 payload — blank form,
  no claim panel, `queryName`-fallback preview (display-spec §11); the
  specs tab and approve/reject flows behave exactly as before.

## Risks / notes

- **Adjudicated (2026-08-31) — the local helper is the answer, not a
  compromise.** D5 now states it explicitly: "the frontend never formats a
  name" governs every surface rendering a *persisted* name, and does not
  forbid previewing the **unsaved form buffer**, which has no server value to
  ask for. So: a **panel-local helper inside `ModelIdentityPanel` only** — not
  exported, no shared `modelName.ts`, no `ModelNameText`, never applied to a
  value that came back from the API. Once a name is saved, the displayed name
  is the server's rendered `name`.
- `WARNING_SUMMARY_PREFIX` is a fragile string contract (ui-spec API-7 /
  OQ-2): a backend rename must touch both repos' locations.
- The one commented cast in `useSaveIdentity` is temporary by contract;
  6.27 deletes it. Any second cast is a stop-and-report.
- Append (`### Step 6.24`) to `shared-knowledge.md`: the local-type
  locations 6.27 must delete, the preview-helper decision, and any fixture
  conventions 6.25/6.27 build on.
