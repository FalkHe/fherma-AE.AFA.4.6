---
phase: 6
step: "6.28"
title: Wire the customer trims and used price live
summary: Sync point S2 — the real variants on the catalogue detail and the real usedPrice on both the detail and the chat cost-estimator result; local type extensions from 6.25/6.26 deleted, rendering byte-identical.
effort: 2
dependencies: ["6.23", "6.26", "6.27"]
---

# Step 6.28 — Wire the customer trims and used price live

**Effort: 2** — a type swap and fixture alignment; both surfaces were built
and tested in 6.25/6.26 and must not change their rendering.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (S2, D9, D10,
D11; read **6.23's `### Step 6.23` Landed decisions entry** for the final
wire shape and whether it committed the regenerated schema) and
`docs/roadmap/phase-6/ui-spec.md` §3.2, §4, §8 (API-2/3/4). Agent:
**frontend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** **starts only after backend 6.23 is merged** (the
`usedPrice` tool/API shape is final). Stack up (`make up`) for the live
smoke; at least one bike researched via `app prices research <slug>` exists
(6.22/6.23's verification data — if none survives, research one approved
bike first).

## Outline

- Schema gate: if 6.23 committed the regenerated
  `frontend/src/api/schema.d.ts`, `make generate-api` must be a no-op;
  otherwise run it and commit the diff **with this step** — the diff must
  be exactly the additive `variants`/`usedPrice` members (D11: every
  pinned field keeps its key and type; `usedPrice` on the **detail**
  resource only, never the list). Anything non-additive is a
  stop-and-report.
- Delete 6.25's and 6.26's local optional members on the catalogue detail
  type: `variants` and `usedPrice` now come from the generated
  `components["schemas"]`; `CatalogueModelRoute` and `ModelSpecTable`
  read the real payload members unchanged.
- `frontend/src/components/toolResults.ts`: align
  `CostEstimatorResult.usedPrice` with the persisted tool-result shape as
  landed (frontend-owned type — must byte-match D11's camelCase names).
- Fixtures (`frontend/src/test/catalogueApi.ts`,
  `frontend/src/test/chatFixtures.ts`) now typecheck against the generated
  detail schema; assertions unchanged — 6.26's component contract
  (absent → nothing, malformed → nothing, `stale` from the flag only)
  holds without edits.

## Verification

- `pnpm lint`, `pnpm typecheck`, `make frontend-test` green without
  touching generated types beyond the gated commit above.
- Live smoke (one pass — M4 acceptance is 6.31's): the researched bike's
  detail page shows the dated snapshot with its source links between the
  spec grid and the article; a bike without a snapshot shows nothing
  there; one chat cost question about the researched bike renders the
  snapshot after the assumptions block; a detail payload with trims shows
  the chip row and delta group.

## Risks / notes

- No component behaviour changes here — if a rendering change seems
  needed, the 6.26 build or the 6.23 shape deviated: stop and report.
- Do not re-prove the M4 criterion or staleness behaviour — 6.31 owns
  them.
- Append (`### Step 6.28`) to `shared-knowledge.md`: confirmation the
  local type extensions are gone and whether this step committed the
  regenerated schema.
