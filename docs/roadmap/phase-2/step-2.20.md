---
phase: 2
step: "2.20"
title: Wire review live (sync point S2)
summary: Regenerate API types and delete the useProductReview stub wholesale — real documents/image/spec-PATCH/transition calls; approve promotes and flips the row via invalidation; image reject wired.
effort: 3
dependencies: ["2.9", "2.13", "2.15", "2.17"]
agent: frontend-dev
track: frontend
---

# Step 2.20 — Wire review live (**sync point S2**)

**Effort: 3** — stub-for-real swap; components must not change.
**Starts only after backend 2.17 and 2.9 are merged** (2.17 implies 2.14, so
review wires against real ingested data; 2.9 provides the documents/images
endpoints). First action: `pnpm generate:api` (needs `app-web` up).

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *JSON:API conventions →
products / documents / product-images* (shapes, the draftSpec PATCH upsert,
image status transitions), *Frontend conventions* (hook exports and query
keys the 2.13 stub pinned). [`ui-spec.md`](ui-spec.md) §6–§9 state tables
for error mapping. Zero deviations; stop and report if one seems necessary.

## Files

- Modify `frontend/src/api/schema.d.ts` (regenerated)
- Rewrite `frontend/src/hooks/useProductReview.ts` (stub deleted wholesale):
  `useProduct(id)` → `GET /api/products/{id}`,
  `useProductDocuments(id)` → `GET /api/documents?filter[product]=`,
  `useProductImage(id)` → `GET /api/product-images?filter[product]=`
  (newest row), `useSaveDraftSpec(id)` → products PATCH `draftSpec` (**send
  the last-fetched draftSpec merged with form values** — the endpoint is
  full-object replace), `useRejectImage()` → product-images PATCH `status`
- Create hook tests (fetch stubbed via the shared `network.ts` helpers)
- Review route/components: **only if unavoidable** — a needed change means
  the stub contract was broken; report it

## Implementation outline

- Invalidations per ui-spec §1 (blanket `["products"]`/`["operations"]`;
  reject additionally `["productImages"]`; spec save
  `["products","detail",id]` + `reset(values)` + success snackbar).
- Approve stays on the page (chip flips via refetch, action bar disappears);
  reject navigates to `/admin`; 422 `loc` mapping per §8.
- Verify the gates against live statuses (ingesting gate with a real
  running operation via SSE).

## Verification

- `pnpm typecheck && pnpm lint && pnpm test` green; no STUB marker remains
  in `useProductReview.ts`.
- In the browser against a really-ingested model: Wikipedia document renders
  with GFM tables and working external links, edit + save a spec value
  (snackbar, refetch shows it), reject image (chip flips), approve →
  confirmation, chip `approved`, Specs tab shows the verified table
  including the edited value.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
