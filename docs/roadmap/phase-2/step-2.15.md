---
phase: 2
step: "2.15"
title: Wire backlog live (sync point S1)
summary: Regenerate API types, delete the useProducts/useOperations stubs wholesale and replace them with real JSON:API calls (list/create/transition incl. retry), live progress via /api/operations + SSE invalidation.
effort: 3
dependencies: ["2.4", "2.8", "2.7"]
agent: frontend-dev
track: frontend
---

# Step 2.15 — Wire backlog live (**sync point S1**)

**Effort: 3** — stub-for-real swap; components must not change.
**Starts only after backend 2.7 is merged** (2.7 implies 2.3 + 2.6 are in
the OpenAPI schema). First action: `pnpm generate:api` (needs `app-web` up).

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *JSON:API conventions →
products / operations* (the response shapes you are wiring against),
*Frontend conventions* (hook exports and query keys — the real hooks must
re-export the same names/types the 2.8 stubs pinned, or update all
consumers, which should not be necessary). Zero deviations; stop and report
if one seems necessary.

## Files

- Modify `frontend/src/api/schema.d.ts` (regenerated)
- Rewrite `frontend/src/hooks/useProducts.ts` (stub deleted wholesale;
  real `useProducts(statusFilter)` → `GET /api/products` walking pages via
  `meta.totalCount`, `useCreateProduct` → `POST`, `useTransitionProduct` →
  `PATCH` status)
- Rewrite `frontend/src/hooks/useOperations.ts` (stub deleted wholesale;
  `useLatestOperationsByEntity` → `GET /api/operations` + `select` reduce)
- Create hook tests (fetch stubbed via the shared `network.ts` helpers)
- `AdminBacklogRoute.tsx` and components: **only if unavoidable** — a needed
  change means the stub contract was broken; report it

## Implementation outline

- Error mapping per ui-spec §5 (409 → `duplicate` field error, 422/5xx per
  state table); mutations invalidate `["products"]` + `["operations"]`;
  create-success clears the status filter param.
- Retry/start = `useTransitionProduct` with `ingesting` (the PATCH
  re-enqueues server-side per the pinned contract).
- Live path: SSE `operation.updated` → invalidation (2.4) → refetch shows
  progress. **Note:** until backend 2.14 lands, a retry PATCH transitions
  the row but enqueues nothing — the full loop is proven in 2.21; here use
  `app operations demo` to drive live updates.

## Verification

- `pnpm typecheck && pnpm lint && pnpm test` green; grep confirms no STUB
  marker remains in `useProducts.ts`/`useOperations.ts`.
- In the browser (stack up, admin): add a model → row appears without
  reload; run
  `docker compose run --rm app-cli app operations demo --bike <slug>` → that
  row's progress cell updates live via SSE; filter round-trips; a failed
  operation row shows retry.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
