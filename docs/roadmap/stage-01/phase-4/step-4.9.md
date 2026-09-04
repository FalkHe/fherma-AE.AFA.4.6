---
phase: 4
step: "4.9"
title: Catalogue wired live + recommendation-card link (S1)
summary: Replace both stub hook files with generated-client implementations, add the SSE invalidations, wrap the Phase-3 recommendation card in its reserved CardActionArea link, and verify the whole customer catalogue end-to-end in the browser.
effort: 2
dependencies: ["4.4", "4.7", "4.8"]
---

# Step 4.9 — Catalogue wired live + recommendation-card link (S1)

**Effort: 2** — the components exist and the wire contract froze at 4.4;
this is hook replacement plus live verification. **Starts only after 4.4 is
merged (S1).**

Binding contracts: `docs/roadmap/stage-01/phase-4/ui-spec.md` and
`docs/roadmap/stage-01/phase-4/shared-knowledge.md`. Agent: **frontend-dev**. Zero
deviations — a deviation (including any shape drift found against the
generated types) is a stop-and-report.

## Outline

- **First action:** regenerate API types — `make generate-api` (the landed
  image-independent sequence). Any diff beyond the expected additive
  `catalogue-models` + relaxed `manufacturers` surface is a
  stop-and-report.
- Delete both stub hook files **wholesale** and rewrite them against the
  generated client (the pinned export names/types are unchanged, so no
  component edits): `useCatalogueModels.ts` (list + manufacturers — types
  re-exported from `components["schemas"][…]`, the 3.6 precedent;
  `placeholderData: keepPreviousData`; the SPA→wire param mapping from
  ui-spec's preamble lives here, `page[size]=24`) and
  `useCatalogueModel.ts` (detail; 404 → `CatalogueError` → the not-found
  state). `imageUrl` thumb derivation via the pinned `_card.webp` →
  `_thumb.webp` suffix swap + `VITE_API_URL` dev prefix (the 3.13/2.20
  precedent).
- `useServerEvents.ts`: `product.updated` additionally invalidates
  `["catalogue"]`; reconnect blanket gains `["catalogue"]` +
  `["manufacturers"]`.
- `RecommendationCard.tsx`: wrap the existing card content in
  `<CardActionArea component={RouterLink}
  to={`/catalogue/${recommendation.motorbikeId}`}>` — Phase-4 ui-spec §6
  (the Phase-3 ui-spec §9 reserved contract); **nothing else changes** in
  that component — its private `imageVariants()` helper stays private (the
  catalogue hooks' own suffix-swap duplication is deliberate).
- Live browser verification per ui-spec §11 against the real dev DB
  (stack up): filters narrow, reload/share reproduces the view, detail
  shows real specs/article/sources/image, admin-approving a model appears
  live via SSE.

## Verification

- `make frontend-test` + lint + typecheck green; stub-era tests still pass
  unchanged (the contract test for the hook shapes).
- In the browser: set 3+ filters → reload → identical view; copy the URL
  into a fresh session → login redirect lands back on the same filtered
  URL; a recommendation card in a Phase-3 consultation navigates to the
  matching detail page; an unapproved model's ULID shows the 404 state.
  **This closes milestone M2** (together with 4.5).

## Risks / notes

- If a renderer needs a key the payload lacks (or vice versa), that is a
  contract bug — report against 4.4/shared-knowledge, do not adapt
  components silently.
- Append decisions (`### Step 4.9`) to `shared-knowledge.md`.
