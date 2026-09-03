---
phase: 6
step: "6.26"
title: Used-price blocks, UI-only
summary: One shared UsedPriceSnapshot component rendering the D11 block on the catalogue detail and inside the chat cost-estimator result; staleness only from the payload's stale flag, absent and malformed states render nothing; still stubs.
effort: 3
dependencies: ["6.25"]
---

# Step 6.26 — Used-price blocks, UI-only

**Effort: 3** — one presentational component with pinned formatting, two
call sites, fixtures and tests; no backend, no new states beyond the spec.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (D10, D11) and
**`docs/roadmap/phase-6/ui-spec.md` §4 (all of it), §7
(`common.usedPrice.*`)**. Agent: **frontend-dev**. Zero deviations — a
deviation is a stop-and-report.

**Environment:** stubs only; `make frontend-test` with the stack down.

## Outline

- **New `frontend/src/components/UsedPriceSnapshot.tsx`** per ui-spec §4.1:
  presentational, data as props, `currency` prop defaulting to `"EUR"`;
  `Intl.NumberFormat(i18n.language, { style: "currency", currency,
  maximumFractionDigits: 0 })` (the exact `ToolResultCostEstimator` idiom);
  the `Intl.DateTimeFormat` `dateStyle: "medium"` as-of date **always
  visible**; `sampleCount === null` → the `sampleUnknown` caption, stated,
  never hidden; every source a MUI `Link` (name verbatim, external-link
  treatment) joined ` · ` in the running caption — never behind a tooltip.
- **Staleness comes only from the payload's `stale` boolean** (D10/D11 —
  the server's verdict via `USED_PRICE_MAX_AGE_DAYS`): no client-side day
  count, no hard-coded figure anywhere; `stale: true` adds the
  warning-coloured caption + `history` icon (colour never the only
  signal), all values keep rendering.
- **Malformed guard** (§4.1): missing `minEur`, `maxEur`, `medianEur`,
  `asOf` or an empty `sources` → the component renders **nothing** (null
  discipline — a price without provenance would read as a fact).
- Catalogue detail (§4.2) — `frontend/src/routes/CatalogueModelRoute.tsx`:
  full-width `<Paper variant="outlined" sx={{ p: 2, mt: 4 }}>` **between
  the image/spec `Grid` and the "About" article**. Absent (`usedPrice`
  null or member missing) → nothing renders — no heading, no "no price
  yet" line. MSRP/price-band chips untouched (D9: new-bike fields).
- Chat (§4.3) — `frontend/src/components/toolResults.ts`:
  `CostEstimatorResult` gains optional `usedPrice` typed exactly per D11
  (`medianEur, minEur, maxEur, sampleCount, asOf, stale,
  sources[{title,url}]`); `ToolResultCostEstimator.tsx` renders
  `<UsedPriceSnapshot currency={result.currency} …/>` **after the
  assumptions block**, separated by `Divider sx={{ my: 1 }}`, inside the
  existing frame (no extra `Paper`). Absent member → today's rendering,
  byte-identical; line items, total, "Estimate" chip and assumptions
  unchanged. Persisted results keep the `stale` the server computed at
  that turn — never recomputed, never re-fetched.
- Typing/stubs: the catalogue detail's `usedPrice` is a local optional
  member until 6.28 (same convention as 6.25's `variants`). Fixtures in
  `frontend/src/test/catalogueApi.ts` (detail with/without `usedPrice`)
  and `frontend/src/test/chatFixtures.ts` (estimator result with/without),
  shaped byte-exactly per D11 / ui-spec §8 API-3/API-4, so 6.28 is a swap.
- i18n: ui-spec §7's `common.usedPrice.*` block, values as pinned.
- Tests via the `network.ts` dispatcher: the §4.3 **Test hooks** list, item
  by item — new `frontend/src/components/UsedPriceSnapshot.test.tsx`
  (range/median/count formatting, unknown-count string, stale caption on
  `true` and none on `false`, every source an external link, nothing on
  empty `sources`), `CatalogueModelRoute.test.tsx` (block present/absent),
  `ToolResultCostEstimator.test.tsx` (after assumptions; without it, DOM
  absent and the rest unchanged).

## Verification

- `pnpm lint`, `pnpm typecheck`, `make frontend-test` green (all §4 test
  hooks covered).
- Dev-server smoke: live catalogue detail and a live chat estimator result
  (no `usedPrice` on today's payloads) render byte-identical to before
  this step — the absent state is the proof the guards hold.

## Risks / notes

- **Both slicing-time flags are resolved — build against the spec as it now
  stands.** §4.1 no longer mentions a `staleDays` key (there is none): the
  caption is `common.usedPrice.stale`, worded without a day figure so the
  server-side threshold can move without a translation change. And
  `frontend/src/components/toolResults.ts` is now an explicit row in the
  ui-spec §0 file map — that is where `CostEstimatorResult` gains its additive
  `usedPrice` member.
- Append (`### Step 6.26`) to `shared-knowledge.md`: the local
  detail-type extension 6.28 must delete, and both fixture locations.
