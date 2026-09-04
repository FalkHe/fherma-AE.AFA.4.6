---
phase: 6
step: "6.27"
title: Wire the admin identity, claim and trims live
summary: Sync point S1 — replace 6.24/6.25's local types and stub fetchers with the generated schema, the real identity PATCH, the real buildingline options endpoint and the landed SSE/queryKeys invalidations; typecheck must stay green without touching generated types.
effort: 3
dependencies: ["6.20", "6.25"]
---

# Step 6.27 — Wire the admin identity, claim and trims live

**Effort: 3** — a deletion-heavy swap (local types → generated schema, stub
fetcher → real endpoint) plus invalidation wiring and one live smoke; the
components themselves do not change.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (S1, D2, D6;
read **6.20's `### Step 6.20` Landed decisions entry** for the exact
buildingline endpoint and wire names) and `docs/roadmap/stage-01/phase-6/ui-spec.md`
§0 (query invalidation), §8 (API-1/2/5/6/7). Agent: **frontend-dev**. Zero
deviations — a deviation is a stop-and-report.

**Environment:** **starts only after backend 6.20 is merged with its
committed `make generate-api` artifact** (`frontend/src/api/schema.d.ts`).
Stack up (`make up`) for the live smoke; the dev DB carries the imported
200-row backlog with `suggestion` populated — pick rows from it.

## Outline

- Gate first: `make generate-api` must produce **no diff**, and
  `pnpm typecheck` must be green against 6.20's committed schema **before
  any change here**. A diff or a type break means 6.20 violated the
  additive rule — **stop and report; never patch or cast around the
  generated types.**
- Delete 6.24's local additive types and the one commented cast in
  `useSaveIdentity` (`frontend/src/hooks/useProductReview.ts`): the
  products resource's `suggestion`, `queryName`, `buildingline`,
  `typeCodes`, `variants` and path-shaped `slug` now come from
  `components["schemas"]` — the PATCH body is typed by the generated
  `identity` block. Error mapping (409 `duplicate-model`, 422 field
  pointers, `incomplete-identity` on approve) stays as built.
- `frontend/src/hooks/useBuildinglines.ts`: swap the provisional `fetch`
  for the generated `apiClient.GET` call on the endpoint 6.20 landed
  (ui-spec API-5 proposed `GET /api/manufacturers/{id}/buildinglines` →
  `string[]`; any admin-readable shape works — the hook adapts). Hook
  name, `queryKeys` builder and `staleTime` unchanged.
- Invalidations per ui-spec §0: a successful identity save invalidates
  `queryKeys.products.detail(id)` (the refetched row is the source of
  truth for the recomputed slug and the server-rendered header name — the
  frontend never formats a name, D5). Confirm the landed `useServerEvents`
  `product.updated` → products-prefix invalidation refreshes the open
  identity tab when the row is written server-side (CLI, extraction) — no
  new SSE plumbing, just verify the existing key prefixes cover the new
  query usage; extend `useServerEvents` only if a key is provably missed.
- Keep the D6 compile-time fence live: the `@ts-expect-error` assertion
  that `suggestion` is not a member of the customer catalogue type now
  points at the **generated** `CatalogueModelAttributes` — this is §2.1's
  wire-boundary half, now real.
- Tests: fixtures for the products resource now typecheck against the
  generated schema (the `stubFetch` dispatcher stays — tests still never
  talk to a backend); delete any fixture member that drifted from the real
  wire names rather than adapting the components.

## Verification

- `make generate-api` → no diff; `pnpm lint`, `pnpm typecheck`,
  `make frontend-test` green — **without a single edit to
  `frontend/src/api/schema.d.ts`**.
- Live smoke (one pass, not the acceptance — M3 behaviour is 6.30's):
  open an imported backlog row's identity tab → the real claim panel
  renders its `suggestion`; edit and save an identity → 200, the slug row
  shows the recomputed path-shaped slug from the refetch; run
  `app catalogue set-identity` against the open row → the tab refreshes
  over SSE without a reload.

## Risks / notes

- **Fixed in the contract (2026-08-31):** the merge-friction list named a
  `frontend/src/api/types.ts` that does not exist. `make generate-api` writes
  `frontend/openapi.json` and `frontend/src/api/schema.d.ts` (Makefile target,
  line 89–91) and both are committed by 6.20. Never create a `types.ts`.
- If 6.20's buildingline endpoint differs from API-5's proposal, adapt the
  hook's fetcher only (the ui-spec allows it); a missing endpoint entirely
  is a stop-and-report.
- Do not re-prove M3 criteria here — 6.30 owns them.
- Append (`### Step 6.27`) to `shared-knowledge.md`: confirmation the
  local types/casts are gone, and the final buildingline endpoint shape as
  wired.
