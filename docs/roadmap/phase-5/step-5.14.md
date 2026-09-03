---
phase: 5
step: "5.14"
title: RegisterRoute tests + OpenAPI type refresh (S1)
summary: Close the RegisterRoute coverage gap (client rules, 409/422 mapping, success path) and regenerate the typed API client once against the 5.5 bounds — expected diff: bounds only, no consumer-visible shape change.
effort: 1
dependencies: ["5.5"]
---

# Step 5.14 — RegisterRoute tests + OpenAPI type refresh (S1)

**Effort: 1** — one new test file plus a regeneration/commit; **this is the
phase's only cross-track sync (S1)** — start only after backend 5.5 is
merged.

Binding contract: `docs/roadmap/phase-5/shared-knowledge.md`. Prior pins:
Phase-1 shared-knowledge (register 409/422 semantics, `AuthError.
validationFields`, submit-only validation), the test conventions in
`frontend/src/test/` (`renderWithProviders`, `stubFetch` — unstubbed
requests throw). Agent: **frontend-dev**. Zero deviations — a deviation is
a stop-and-report.

**Environment:** backend 5.5 merged; for `make generate-api` the compose CLI
profile is enough (stack may be down).

## Outline

- New `frontend/src/routes/RegisterRoute.test.tsx`: client-rule failures
  (short username, pattern, short password, mismatch — submit-only, first
  invalid field focused), server 409 → username field error, server 422 →
  `validationFields` mapping, network failure → general Alert, success path
  (auth cache updated / navigation).
- `make generate-api`; review the `frontend/openapi.json` +
  `frontend/src/api/schema.d.ts` diff: 5.5's bounds may appear
  (min/max/pattern annotations); **no TS shape change is expected** — if a
  consumer-visible type changes, stop and report. Commit the refreshed
  artifacts (the qa-checklist drift rule).

## Verification

- `pnpm lint && pnpm typecheck && pnpm test` green;
  `git diff --exit-code frontend/src/api/schema.d.ts` after a second
  `make generate-api` run (no drift).

## Risks / notes

- Do not modify `RegisterRoute.tsx` itself — this is a coverage step; a
  found bug is a stop-and-report.
- Append (`### Step 5.14`) to `shared-knowledge.md` only if the generated
  types moved in any consumer-visible way (they shouldn't).
