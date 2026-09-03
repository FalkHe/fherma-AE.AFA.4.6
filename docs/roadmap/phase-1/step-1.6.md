---
phase: 1
step: "1.6"
title: Frontend auth wiring
summary: Regenerate API types, add CSRF/401 client middleware, replace the useAuth stub with real /auth/* calls, and connect login/register/logout/guards end to end.
effort: 4
dependencies: ["1.3", "1.4"]
agent: frontend-dev
track: frontend
---

# Step 1.6 — Frontend auth wiring

**Effort: 4** — the integration step: codegen, client middleware, the real
`useAuth` hooks, and end-to-end verification of the whole phase.

**This is the only cross-track sync point of Phase 1: it starts only after
backend step 1.3 is merged.** First action: `pnpm generate:api`.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) (API contract, cookies/CSRF,
frontend conventions) and [`ui-spec.md`](ui-spec.md) §1–§4 state tables.
Step 1.5 (CLI) is not needed to implement this step, but the final phase
done-check below uses it.

## Files

- Regenerate `frontend/src/api/schema.d.ts` (`pnpm generate:api`; commit it)
- Create `frontend/src/queryClient.ts` — extract the existing `QueryClient`
  instance from `main.tsx` so the client middleware can import it (pure
  move; do it as the first change)
- Modify `frontend/src/api/client.ts` — CSRF onRequest + 401 onResponse
  middleware per shared-knowledge *Frontend conventions*
- Modify `frontend/src/hooks/useAuth.ts` — **delete the stub wholesale**;
  real query + mutations
- Modify `frontend/src/routes/LoginRoute.tsx`,
  `frontend/src/routes/RegisterRoute.tsx` — server-error display by status
  code, redirect handling, authenticated-user redirect
- Modify `frontend/src/main.tsx` — import the query client from its new file

## Implementation outline

- **Middleware** (`api/client.ts`):
  - onRequest: for methods outside `{GET, HEAD, OPTIONS}`, read the
    `csrf_token` cookie from `document.cookie` (small local helper) and set
    the `X-CSRF-Token` header.
  - onResponse: on 401 from any path **not** starting with `/auth/`,
    `queryClient.setQueryData(["auth", "me"], null)` — `RequireAuth` then
    redirects. `/auth/` paths are excluded so a failed login doesn't loop.
- **`useAuth`**: TanStack Query on `GET /auth/me`, key `["auth", "me"]`,
  `retry: false`, `staleTime: 5 * 60_000`; a 401 resolves to `user: null`
  (not an error). Returns the pinned
  `{ user, isLoading, isAuthenticated }` shape.
- **`useLogin`**: `POST /auth/login` with `{username, password, rememberMe}`;
  on success `queryClient.setQueryData(["auth", "me"], userResponse)`.
- **`useRegister`**: `POST /auth/register`, then chain the login call with
  the same credentials (`rememberMe: false`).
- **`useLogout`**: `POST /auth/logout`; on settle (success **or** 401)
  `queryClient.clear()` and `navigate("/login", { replace: true })`.
- **Screens**: login success →
  `navigate(location.state?.from?.pathname ?? "/", { replace: true })`;
  401 → `auth.errors.invalidCredentials` alert (clear password, refocus
  username); register 409 → `auth.errors.usernameTaken` on the username
  field; network/5xx → `auth.errors.serverError`; full mapping in ui-spec
  §1/§2. Add the authenticated-user redirect
  (`user` present → `<Navigate to="/" replace />`) to both auth pages —
  deliberately deferred from step 1.2.

## Verification

- `pnpm generate:api` then `git diff --exit-code frontend/src/api/schema.d.ts`
  is clean after commit; `pnpm tsc --noEmit` passes.
- Fresh browser profile: `/` redirects to `/login` (guard spinner, no
  content flash). Visiting a deep link while signed out, then logging in,
  lands on the originally requested route.
- Register a new user → auto-logged-in, app shell shows the username in the
  account menu.
- DevTools network: logout request carries `X-CSRF-Token`; sign out → back
  at `/login`; `GET /auth/me` now returns 401.
- Login **with** "Remember me" → close and reopen the browser → still
  signed in. Without it → a new browser session redirects to `/login`.
- Visiting `/login` while signed in → immediately at `/`.
- **Phase-1 done-check** (needs step 1.5):
  `docker compose exec app-web app users set-role <name> admin` + reload →
  Admin nav item appears; `/admin` shows the admin shell; a second,
  non-admin account sees neither.

## Risks / notes

- **If the generated types don't match the pinned contract, stop and flag
  the backend deviation — never hand-patch `schema.d.ts`.**
- Components from 1.2/1.4 must not need edits beyond the listed
  error-display/redirect wiring — if they do, the stub shape was violated;
  fix the hook, not the components.
