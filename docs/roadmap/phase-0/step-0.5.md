---
phase: 0
step: "0.5"
title: Typed API client pipeline and live health status
summary: The openapi-typescript → openapi-fetch pipeline (generate:api script, committed schema.d.ts, typed client) plus a HealthStatus component proving the full loop against GET /health.
effort: 3
dependencies: ["0.3", "0.4"]
---

# Step 0.5 — Typed API client pipeline + live health status

**Effort: 3** — the frontend half of the type-generation pipeline as one well-bounded concern (codegen + typed client + first consumer), proving the full backend→types→UI loop end to end, including the 0.1 CORS setup.

## Architect's outline

- Codegen pipeline: `generate:api` package script → `docker compose exec app-web app openapi export > openapi.json && openapi-typescript openapi.json -o src/api/schema.d.ts`; generated types committed.
- `frontend/src/api/schema.d.ts` (generated, committed) + `frontend/src/api/client.ts` — `openapi-fetch` client with `baseUrl` from `VITE_API_URL` and a middleware stub setting `credentials: "include"` (CSRF header slot added in Phase 1).
- Home route gains a `HealthStatus` component: TanStack Query hook calling `GET /health` via the typed client, with loading spinner / OK chip / error state; strings via i18n. Dev calls go cross-origin using step 0.1's CORS setup — simpler than a Vite proxy and exercises the cookie/CORS path Phase 1 needs.
- Verification requires the stack running, which requires the user-created `.env` (see 0.1); if it is missing, stop and ask the user — never create it.
- Agent assignment: **frontend-dev**.

## Verification

- `pnpm generate:api` regenerates `schema.d.ts` with zero diff after commit; `tsc --noEmit` passes.
- Open `http://localhost:5173`: health indicator shows "Backend: OK"; stopping `app-web` flips it to the error state.

## Risks / notes

- Committed generated types will drift; document a regenerate + `git diff --exit-code` convention in the QA checklist (formal CI enforcement out of scope for Phase 0).
