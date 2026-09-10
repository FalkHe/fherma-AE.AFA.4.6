---
title: "Phase 0 — shared knowledge"
phase: 0
created: 2026-09-08
---

# Phase 0 — shared knowledge

Binding contract for every agent working in phase 0. Read this before the step
file. Where this document and an agent report disagree, this document wins;
where this document and the code disagree, the code wins and this document is
corrected.

Phase 0 delivers the scaffolding: both trees, authentication, a blank
authenticated home page. No game content, no agent, no RAG.

## Steps

| Step | Contents | Status |
|---|---|---|
| [step-0.1.md](step-0.1.md) | Backend + frontend skeletons, `auth` and `users` modules, blank home page | spec |

## Landed decisions

Append here. One heading per decision, newest last. State the decision and the
one-clause reason. Never rewrite another agent's entry.

### D1 — Modular layout, both trees

Organised by domain module, not technical layer. Backend: `app/main.py`,
`app/core/`, `app/api/v1/router.py` (combines modular routers and does nothing
else), `app/modules/<module>/{models,schemas,routes,service}.py`, with
`backend/tests/<module>/` mirroring modules one-to-one. Frontend:
`src/core/`, `src/components/` (genuinely shared UI only),
`src/modules/<module>/{components,hooks,routes}/`. Anything in `core/` needs
two or more module callers; a single-caller helper lives in its caller's
module. Reason: a reader must be able to delete a module without hunting
through six shared directories.

`frontend/src/api/` is the single exception to the frontend scheme: it holds
generated artefacts only, and it exists because the `Makefile` writes there.

**The placement bar.** It is satisfied by **two or more module callers**,
counted as *modules that actually render or import the file* — not by a file
that *could* be reused, and not by counting routes or slots. The shared file
must itself import nothing from any of them. One module caller means the file
lives in that caller's module.

The bar governs **helpers and components**. It does not govern the per-app
singletons `core/` exists for — the HTTP client, the query-client factory, the
theme, the i18n instance — whose placement is architectural, not a reuse
claim; those are mounted once by `main.tsx` or are the repo's single seam for a
concern, and they may legitimately have one importer.

Two worked examples, both from step 0.1, both there to be argued against later:

- **`AuthCard`** — two callers (`SignInRoute`, `SignUpRoute`), both inside
  `modules/auth`. It stays in `modules/auth/components/`. Two callers is not
  two *module* callers.
- **`AppShell`** — `frontend/src/modules/home/components/AppShell.tsx`. `/` is
  the only route that renders it, so `HomeRoute` is its sole caller, and it is
  `HomeRoute` — not `modules/auth` — that imports `SignOutButton` to fill the
  `action?: ReactNode` slot. An owner ruling had placed it in
  `src/components/` on the claim of "two module callers on day one"; that claim
  was false and the rule overrode the ruling. Its shape is unchanged (`title`,
  `action?: ReactNode`, `children`, and no import from any module), which is
  what makes it promotable: it **graduates** to `src/components/` unchanged the
  moment a second module renders it. That is the expected path for shared UI
  here — born in its module, promoted on evidence — and `src/components/` is
  therefore **empty in phase 0**.

Cross-module imports are named in the step spec, never implicit. In step 0.1
there is exactly one on the frontend: `modules/home` imports `SignOutButton`,
`useSignOut` and `useCurrentUser` from `modules/auth`. On the backend, `auth` calls
`users.service` functions.

### D2 — Auth is server-side sessions

Username + password, Argon2 hashing, opaque session token stored as a SHA-256
hash in a Postgres `sessions` table, token delivered in an `HttpOnly` cookie
named `session`. One persona (`user`); no role column, no admin. Reason: the
project needs identity for per-user game state, not an authorisation system.

### D3 — CSRF is a synchroniser token in a response header

The CSRF token is generated with the session, stored in `sessions.csrf_token`,
delivered to the client in the `X-CSRF-Token` **response** header on register,
sign-in and `GET /users/me`, and echoed by the client in the `X-CSRF-Token`
**request** header on every cookie-authenticated mutation. It is never put in
a cookie and never in a response body. Reason: a cross-site page cannot read a
CORS-protected response header, and comparing the header against the database
row avoids the double-submit cookie-injection weakness.

Unauthenticated mutations (`register`, `sign-in`) are exempt: there is no
session to protect.

### D4 — Wire shape is plain REST with camelCase

Resource objects are returned directly, no document envelope. Keys are
camelCase on the wire via a shared Pydantic base
(`alias_generator=to_camel`, `populate_by_name=True`). Errors use one envelope,
`{"error": {"code", "message", "details"}}`, with stable domain codes and a
catch-all 500 handler. No JSON:API layer. Reason: one wire convention, and the
generated TypeScript client is then idiomatic without a mapping layer.

### D5 — No background job runner, no Redis

Every operation is request-scoped or a CLI one-off. Anything that would once
have been a queued job is either a synchronous request or a Typer command.
Reason: the deployment has neither service, and the agent's work is
interactive.

### D6 — Logs go to stderr

Application logging (structlog) writes to stderr, not stdout, so that
`app openapi export > frontend/openapi.json` produces valid JSON. Stdout is
reserved for command output. Reason: `make generate-api` redirects stdout.

### D7 — No `SESSION_SECRET`

Session tokens are 256-bit random values stored hashed; the CSRF token is a
random value stored on the session row. Nothing is signed, so no signing
secret exists. Reason: a setting with no consumer is an invitation to a second
auth mechanism.

Declared settings for phase 0 are exactly five: `ENVIRONMENT`, `LOG_LEVEL`,
`DATABASE_URL`, `SESSION_TTL_SECONDS`, `FRONTEND_ORIGIN`. There is no sixth.
`extra="ignore"` is what lets the undeclared model and Langfuse keys sit in
`.env.dist` harmlessly — Compose passes the whole `.env` to `app-web`, and an
undeclared key must not be an error.

`.env.dist` and `README.md` are settled and are the owner's files: no agent
edits them. A fresh checkout needs `cp .env.dist .env` and nothing more —
every default works out of the box.

### D8 — Transactions belong to services

`get_db_session` yields a session and rolls back on exception; it never
commits. Service functions own the transaction boundary and call
`await db.commit()` themselves. Routes contain no `commit`, no `add`, no
`execute`. Reason: one place per unit of work, and the route stays a thin
translation layer.

### D9 — The async engine is never built at import time

`get_engine()` and `get_sessionmaker()` in `app/core/db.py` are `@lru_cache`d
and are called only from the `get_db_session` dependency. No lifespan handler
touches them. Reason: the cache is keyed process-wide, not per event loop, so
building an engine outside the serving loop breaks pytest — see
`.claude/skills/qa-checklist/SKILL.md`.

The backend suite stays synchronous (`TestClient`, `CliRunner`), overrides
`get_db_session` with a stub, and monkeypatches the pinned service functions.
No `pytest-asyncio`.

### D10 — Service function signatures are contract

Because the test suite is written against them before the implementation
exists, the exported function names and signatures of each module's
`service.py` are part of the spec, not an implementation detail. Changing one
is a contract change and needs a spec amendment. Reason: it is the only seam
that lets QA author route tests without a database.

**The call style is part of the seam.** Routes and dependencies hold a
*module* reference — `from . import service`, or
`from app.modules.users import service as users_service` across modules — and
call `service.create_user(...)`. **Nothing imports a service function by
name**: `from .service import create_user` rebinds the function into the route
module, and `monkeypatch.setattr(app.modules.users.service, "create_user", …)`
then silently misses.

### D11 — `frontend/openapi.json` is a spec artefact, `schema.d.ts` is generated

The architect commits `frontend/openapi.json` expressing the pinned wire
contract as the OpenAPI 3.1 document FastAPI will produce. frontend-dev
generates `src/api/schema.d.ts` from it with `pnpm generate:api` and commits
the result — so no hand-written type ever masquerades as a generated one.
After the backend lands, `make generate-api` regenerates both from the running
app; a diff in `schema.d.ts` is a backend contract violation, and the backend
is what gets corrected. Reason: `make generate-api` needs a running `app-web`,
which does not exist while the frontend is being built in parallel.

Consequences that bind backend-dev: route function names determine
`operationId`s; Pydantic schema class names determine component names; each
route declares its failure `responses=` explicitly; route functions carry no
docstrings and fields carry no `description=`.

### D12 — TypeScript is pinned at 5.9

Not 6.x or 7.x. It is the only line satisfying every peer range in the
frontend tree: `typescript-eslint@8` requires `>=4.8.4 <6.1.0` and
`openapi-typescript@7` requires `^5.x`. Reason: a peer conflict in the
lockfile is worse than being two majors behind on a type checker.

### D13 — i18n from day one, one language

react-i18next with **one namespace per frontend module plus `common`**,
`defaultNS = "common"`, resources in
`src/core/i18n/locales/en/{common,auth,home}.json`, and
`src/core/i18n/i18n.d.ts` declaring `CustomTypeOptions` so a wrong key fails
`pnpm typecheck`. Every user-facing string goes through a key; no literal copy
in components, and no number written into the JSON — numbers are interpolated
from the owning module's constants. No language detector, no HTTP backend, no
switcher until a second language exists. Reason: retrofitting keys is
expensive, adding a switcher is cheap, and per-module namespaces follow the
module boundary already in place.

### D14 — Material UI is **v9**: `"@mui/material": "^9.4.0"`

That exact constraint goes in `frontend/package.json`. Verified against the
registry: `latest` is `9.4.0` and `7.3.11` sits as `latest-v7`.

**This matters because `docs/roadmap/phase-0/ui-spec.md` was written against
v7 and says so.** Its API choices are all valid on v9, so follow its v9
phrasing and **never** its v7 fallbacks:

| Use (v9) | Not the v7-era fallback |
|---|---|
| `<Button loading>` | `<LoadingButton>` from `@mui/lab` |
| `slotProps={{ htmlInput: … }}` | `inputProps={{ … }}` |
| `createTheme({ cssVariables: true, colorSchemes: { light: true, dark: true } })` | a `useMediaQuery("(prefers-color-scheme: dark)")` theme |

Two further v9 breaking changes: layout components (`Box`, `Stack`, `Grid`) no
longer accept system props — use `sx` — and `Grid` takes `size`
(`size={{ xs: 12, sm: 6 }}`), with `item` and `GridLegacy` removed.

Otherwise plain MUI: `ThemeProvider` with `CssBaseline` **inside** it, no
palette, typography or component overrides, no custom design system, no colour
literal anywhere under `src/`. Enabling the two colour schemes is theme
correctness, not visual design. In MUI v9 the layout components
no longer accept system props: spacing goes through `sx`, and `Grid` uses
`size`. Reason: visual design is not being evaluated yet.

### D15 — Declarative routing only

`react-router` v8 (there is no `react-router-dom` package any more) with
`<Routes>` / `<Route>`. No data routers, no loaders, no actions:
authentication state comes from the TanStack Query cache, keyed
`["currentUser"]`. Reason: one source of truth for auth state, and no second
data-fetching mechanism.

### D16 — `ui-spec.md` is binding alongside the step spec

For anything user-facing, the phase's `ui-spec.md` is the authority on screen
composition, MUI component choice, every visual state, validation timing and
messaging, copy, i18n keys, focus management and the a11y baseline. The step
spec is the authority on the wire contract, URLs, the file tree, data-access
surfaces and the parallelisation split. Where the two collided in step 0.1 the
rulings are tabulated in `step-0.1.md` §6.3, and the answers to `ui-spec.md`
§11 are in §6.4. Reason: two documents, two owners, one resolution table — not
two half-answers.

### D17 — Frontend routes are `/signin` and `/signup`

Not `/sign-in` / `/sign-up`. The API paths remain hyphenated
(`POST /api/v1/auth/sign-in`, `.../sign-out`): they are different namespaces
and there is no reason to make one follow the other.

### D18 — Cookies and headers go on the injected `Response`

Routes and dependencies never construct or return a `Response`. They take
`response: Response`, mutate its cookies and headers, and return the response
model or `None`; FastAPI merges those headers into the real response, including
a bodiless `204`. Two consequences that are easy to get wrong:

- A dependency that **raises** has its injected `Response` discarded, so
  `require_auth` cannot clear the `session` cookie itself. The
  `SESSION_EXPIRED` clearing is done by the `ApiError` handler in
  `register_error_handlers`, on the `JSONResponse` it builds, for that code
  only. It is the one place in the codebase that clears the cookie on a
  failure path, and it covers every protected route at once.
- `return Response(status_code=204)` from sign-out bypasses the header merge
  and loses the cookie-clearing `Set-Cookie`. Sign-out returns `None`.

Reason: one rule, and the two places where FastAPI's response plumbing does
not do what the naive code implies.

### D19 — `AuthContext` is two queries, in a fixed order

There are no ORM `relationship()`s, so `UserSession` has no `.user`.
`require_auth` calls `auth.service.resolve_session` and then
`users.service.get_user_by_id`, in that order; either returning `None` is
`SESSION_EXPIRED` (an absent cookie is `NOT_AUTHENTICATED` and reaches
neither). `require_csrf` makes no service call. Reason: QA stubs the seam and
must know how many functions it is stubbing.

### D20 — The frontend provider stack lives in `main.tsx`; `App.tsx` is routes only

Nesting, outermost first: `StrictMode` → `ThemeProvider theme noSsr` (with
`CssBaseline` as its first child) → `I18nextProvider i18n` →
`QueryClientProvider` (one `createQueryClient()` at module scope) →
`BrowserRouter` (from `react-router/dom`) → `<App />`. `App.tsx` renders
`<Routes>` and nothing else: no provider, no router, no layout. Reason: a test
can then render `<App />` inside its own provider wrapper with a
`MemoryRouter`, and a nested router throws.

### D21 — One owner per redirect to `/signin`

`core/api/client.ts` keeps its single CSRF job: no `QueryClient` reference, no
cache write, no global 401 interceptor (the query client is a factory and
`core/api` cannot reach the instance).

- **Deliberate sign-out** is owned by `modules/auth/hooks/useSignOut.ts`. It
  navigates to `/signin` (`replace`) **first**, then clears the CSRF token and
  writes `{ user: null, sessionExpired: false }` into `["currentUser"]`, all in
  one handler — one commit in which
  the location is already `/signin`, so `RequireAuth` is unmounted and never
  redirects. No router state, therefore no "session ended" warning.
- **Expiry while the tab is open** is owned by
  `modules/auth/components/RequireAuth.tsx`, triggered only by the
  `["currentUser"]` query resolving to no user, and carries
  `{ from, reason: "sessionExpired" }` exactly when the server's `401` said
  `SESSION_EXPIRED` (D27).
- A **401 on the sign-out request** is the first case, not the second: the
  session is already gone, so it runs the success handler and shows no error.
  `auth:signOut.error` is for `403`, `5xx`, an unmapped code and `NETWORK`.

Reason: two mechanisms driving one redirect is how a deliberate sign-out ends
up telling the user their session expired.

### D22 — No server-422 → field-error mapping in the frontend

A `422` maps to `common:errors.unexpected` like any unmapped failure. The
client mirrors the server's validation rules, so a 422 from a form means a
client bug, not a user mistake; `details.fields` stays on the wire for
operators and later steps, and no frontend code reads it. Reason: an
unreachable layer with no acceptance criterion is worse than no layer.

### D23 — Backend dev dependencies live in `[dependency-groups] dev`

Not `[project.optional-dependencies]`. `uv sync --locked` in
`docker/backend.Dockerfile` installs default dependency **groups** and no
extras, so as an extra `pytest` and `ruff` would be missing from the image and
`make backend-test` / `make backend-lint` would fail for a packaging reason.

### D24 — `frontend/src/test/**` belongs to qa-frontend

The shared helpers are test infrastructure with exactly one consumer, so
qa-frontend owns them outright and chooses their signatures. frontend-dev
creates no file there; it only points `vitest.config.ts`'s `setupFiles` at
`./src/test/setup.ts`. Three constraints survive the boundary: exactly **one**
fetch dispatcher, installed in the setup file at startup and never replaced
(`openapi-fetch` captures `globalThis.fetch` when `core/api/client.ts` is
evaluated); an unstubbed request **throws**; and `VITE_API_URL` is undefined
under vitest, so the client's `baseUrl` is `undefined` and request paths are
relative (`/api/v1/...`).

### D25 — A failed sign-in logs the submitted username at INFO

It is the only user-supplied value that reaches a log in phase 0, and it is
accepted: it is what an operator needs to read a credential-stuffing pattern.
The password is never logged. Recorded so it is not rediscovered as a leak —
and so a later step that adds request logging knows the bar it is being held
to.

### D26 — A `500` reaches the browser without CORS headers

FastAPI's catch-all `Exception` handler runs on `ServerErrorMiddleware`, which
sits **outside** `CORSMiddleware`, so the `500 INTERNAL_ERROR` envelope is sent
without `Access-Control-Allow-Origin`. The browser therefore rejects it and
the SPA sees a *network* failure (`common:errors.network`), not
`common:errors.unexpected`. The envelope is still correct on the wire and
`curl` sees it; only the browser path differs. Not worth a middleware
inversion in phase 0 — recorded so nobody debugs it twice.

### D27 — The expiry signal is the server's error code, not a client ref

`GET /api/v1/users/me` distinguishes `SESSION_EXPIRED` (a cookie was sent and
resolved to nothing — expired, swept, signed out elsewhere, or forged) from
`NOT_AUTHENTICATED` (no cookie was sent). The frontend reads the reason off
that code: the `["currentUser"]` query caches
`{ user: UserRead | null; sessionExpired: boolean }`, `useCurrentUser` exposes
`sessionExpired`, and `RequireAuth` adds `reason: "sessionExpired"` exactly
when it is true. **There is no `wasAuthenticated` ref and no client-side
memory of having been signed in.** Reason: one mechanism instead of two, server
truth instead of state that must be kept in sync, and showing a first-time
visitor "Your session ended." becomes unrepresentable rather than merely
tested-against.

Accepted consequence, pinned in `step-0.1.md` §5.6: a visitor arriving with a
long-dead cookie sees the expiry warning, because the server cannot tell that
from a session that ended a second ago — and from the visitor's point of view
the message is true.

## Known future work

Recorded so it is not rediscovered as a bug.

- **`app sessions prune`.** Expired rows in `sessions` are never removed:
  `resolve_session` treats a past `expires_at` as "no session" and performs no
  write, and there is no job runner to sweep with (D5). The fix is a Typer
  command deleting rows where `expires_at < now()`, run on demand. Deliberately
  out of scope for step 0.1.
- **The `project-vision.md` out-of-scope line is settled.** It now reads
  "multiplayer, maps, voice" — `authentication` and `external APIs` are both
  gone, so there is no longer a contradiction with the character-generation
  agent of its §1 or with `135.md`'s external-API bonus target. Nothing to do;
  recorded because earlier drafts of this file and of `step-0.1.md` §10 OQ-C
  described that line as still listing `external APIs`.
- **The OpenRouter and Langfuse keys are undeclared on purpose.** They sit in
  `.env.dist` and are swallowed by `extra="ignore"` (D7). The step that first
  calls a model promotes them into `Settings` as declared fields — at which
  point the "exactly five settings" statement in D7 stops being true and must
  be amended, not worked around.
- **`useSignIn` writes the cache before it navigates.** Its success handler
  sets `["currentUser"]` and then calls `navigate(from ?? "/")`. Once the cache
  holds a user, `RequireAnonymous` — still mounted on `/signin` — can win the
  race with its own `<Navigate to="/" replace>`, so the user lands on `/`
  rather than on `from`. Invisible in phase 0 because `/` is the only protected
  route and `from` is therefore always `/`. **The step that adds a second
  protected route must flip the order: navigate first, write the cache after**,
  the way `useSignOut` already does (D21).
- **`core/api/errors.ts`'s `unwrap()` conflates programming errors with network
  failures.** Its `catch { throw networkFailure() }` catches *everything*
  thrown while making the request — not just genuine connectivity failures.
  qa-frontend hit this directly while root-causing its own test infrastructure
  bug: with `VITE_API_URL` unset, `openapi-fetch` built `new Request("/api/v1/...")`
  with no base URL. Node's `Request`/`URL` throw synchronously on a
  scheme-relative URL where a browser would silently resolve it against
  `document.baseURI`; that `TypeError` was swallowed by `unwrap()`'s catch-all
  and surfaced on screen as `{code: "NETWORK", status: 0}` — indistinguishable
  from a genuinely unreachable server. This is a real robustness gap (a
  programming/config error masquerades as a network failure in production,
  not just in tests), but it is deliberately unfixed for now: UI-29 and D34
  are green against the current behaviour, and no criterion covers
  distinguishing this case. The phase that next revisits API error handling
  should start from this diagnosis rather than rediscovering it — e.g. narrow
  the catch to the fetch call itself, or classify synchronous construction
  errors separately from a rejected fetch promise.

### D32 — `BrowserRouter` (and `Link`) import from `"react-router"`, not `"react-router/dom"`

`step-0.1.md` §6.2 said `BrowserRouter` comes from `react-router/dom`. Verified
against the installed `react-router@8.3.1` package: that subpath's type
declarations export only `RouterProvider`, `HydratedRouter` and the RSC/SSR
helpers — no `BrowserRouter`, no `Link`. Both are exported from the package
root (`"react-router"`) in this version, confirmed against
`node_modules/react-router/dist/production/index.d.ts` and consistent with
`src/test/render.tsx`, which already imports `MemoryRouter`, `useLocation` and
`useNavigate` from `"react-router"`. `main.tsx` and every route component
import `BrowserRouter`/`Link` from `"react-router"` accordingly; `"react-router/dom"`
is not imported anywhere in this step. A later step must not "fix" this back
to match the stale spec text — the code and the installed package are the
source of truth here (`.claude/CLAUDE.md`: "where the code and a doc
disagree, the code wins").

### D33 — `eslint.config.js` selects only `rules-of-hooks` + `exhaustive-deps` from `eslint-plugin-react-hooks` (superseded — full preset restored)

**Update:** this narrowing has been reverted. `eslint.config.js` now spreads
the full `reactHooks.configs.recommended.rules` again (16 rules, including the
React Compiler diagnostic suite). Original rationale and its resolution kept
below for the record — do not narrow the preset again for the reason
described here, since it no longer applies.

Original text: the plugin's `recommended` (and `recommended-latest`) flat
configs at `^7.1.0` bundle the full React Compiler diagnostic suite
(`react-hooks/refs`, `set-state-in-render`, `purity`, `immutability`, …), not
just the traditional two hook-correctness rules. This project does not build
with the React Compiler, and the `refs` rule in particular flags
`src/test/render.tsx`'s deliberate `ref.current = value` assignment during
render (a documented, intentional "live ref" pattern qa-frontend uses to read
the freshest router location without a stale closure). `eslint.config.js`
therefore set `"react-hooks/rules-of-hooks": "error"` and
`"react-hooks/exhaustive-deps": "warn"` explicitly instead of spreading
`reactHooks.configs.recommended.rules`.

**Resolution:** qa-frontend re-examined the `ref.current = value` during
render in `src/test/render.tsx` and determined it was not actually necessary;
it moved the sync into a bare no-deps `useEffect` instead. It then verified
the fix with a throwaway config spreading the plugin's real
`recommended.rules` and confirmed zero problems across the whole project, and
separately confirmed the suite still passes 53/53 (`getPathname()` is only
read via `waitFor` or after a `user-event` interaction, both of which already
flush effects). With the underlying conflict gone, `eslint.config.js` was
widened back to the full preset and reverified clean (`pnpm lint`,
`pnpm typecheck`, `pnpm build`). The React Compiler diagnostics are therefore
deliberately on again; don't narrow the preset unless a genuine new conflict
with them appears.

### D34 — `RequireAuth`'s error state always renders `common:errors.network`

`useCurrentUser()`'s pinned return shape (`user`, `sessionExpired`,
`isPending`, `isError`, `refetch` — step-0.1.md §6.2 "Hooks contract") does not
expose the failed query's error code, so `RequireAuth` cannot distinguish a
`NETWORK` failure from a 5xx when `isError` is true. `ui-spec.md` §6.3 lists
both `common:errors.network` and `common:errors.unexpected` as possible copy
for that row without pinning which applies when; the only acceptance
criterion that exercises this state (UI-29) is the network case. Resolved by
always rendering `common:errors.network` for `isError` at this guard — sitting
alongside `D26`'s existing note that a real `500` reaches the browser without
CORS headers and therefore already presents to `fetch` as an opaque network
failure, so the `unexpected` branch is effectively unreachable here in
practice. If a later step needs to tell the two apart, `useCurrentUser` must
grow an `error`/`code` field first — that is a contract change, not a local
fix.

### D35 — Dynamic i18n keys: `modules/auth/validation.ts` exports `translateFieldError`

Field-validation and server-mapped field errors carry their i18n key as a
runtime string (`FieldValidationError.key`), which `react-i18next`'s generated
`t()` type (D13/UI-32) cannot accept directly — the compile-checked key union
only takes literals. `translateFieldError(t, error)` is the one place that
casts (`as any`, narrowly scoped with a comment) to bridge the two; both
`SignInForm` and `SignUpForm` call it instead of `t()` directly for
field-level messages. A later module with the same "dynamic key from a data
structure" shape should reuse this pattern rather than re-inventing a cast at
each call site.

### D28 — `verify_password(hashed, password)` — argument order pinned

Mirrors argon2-cffi's own `PasswordHasher.verify(hash, password)` (hash
first). qa-backend's `tests/core/test_security.py` was written against this
order; use it exactly. Recorded per the owner's ruling in `step-0.1.md`.

### D29 — Cross-module schema imports: request schemas live with the verb, `UserRead` lives with the resource

`app/modules/auth/schemas.py` owns `RegisterRequest` and `SignInRequest` (the
auth verbs, matching the `/auth` routes that consume them);
`app/modules/users/schemas.py` owns `UserRead` (the user resource). `auth`'s
three routes (`register`, `sign_in`, `sign_out` — the last returns nothing)
import `UserRead` from `users.schemas` to type their response. This is a
cross-module import of another module's public wire schema, not its
`service.py`/`models.py` internals, so it does not go through a service
function; it is the same category of reuse as `auth` calling
`users.service.verify_credentials`, just for a response shape instead of a
query. Reason: `auth/schemas.py` would otherwise be empty despite being in
the pinned file tree, and duplicating `UserRead` in both modules would create
two response shapes for one resource.

### D30 — `sign_out`'s full parameter list is `(request, response, auth, db)`, not the two-parameter illustration in §6.1

`step-0.1.md` §6.1 writes `sign_out` as `async def sign_out(response: Response,
auth: CsrfAuth) -> None` while illustrating the "cookies and headers" rule
(routes never construct a `Response`, they mutate the injected one). Taken
literally that signature cannot satisfy §5.5 ("the session row is deleted"):
`auth_service.delete_session(db, *, token)` needs both a live `db: DbSession`
and the raw cookie token, and `AuthContext` (from `require_auth`) exposes only
the resolved `user`/`session` rows, never the raw token — only the request
cookie has it. The implemented signature is
`async def sign_out(request: Request, response: Response, auth: CsrfAuth, db: DbSession) -> None`,
reading `request.cookies["session"]` for the token to revoke. This matches
qa-backend's `tests/auth/test_sign_out.py`, which stubs
`auth_service.delete_session` and asserts the old cookie stops working
afterwards — unreachable if the route never calls it. Treated as filling an
underspecified illustration, not as a contract deviation, since no pinned
name or wire shape changes; flagged here in case the owner intended something
narrower.

### D31 — Dev-dependency addition and a transitive-version constraint, both required to make `filterwarnings = ["error"]` usable

As of this step's `uv lock` (package registry state, 2026-09), the pinned
floor `fastapi>=0.141.1` resolves to `starlette==1.6.0`, which changed its
`TestClient` to prefer an `httpx2` package and, absent it, imports plain
`httpx` behind a `warnings.warn(StarletteDeprecationWarning, ...)` — and
separately, at module scope, references the now-deprecated
`anyio.abc.BlockingPortal` alias, which `anyio>=4.15` turns into a
`DeprecationWarning` on attribute access. Both warnings fire the instant
`fastapi.testclient.TestClient` is imported — i.e. on collection of every
test module via `tests/conftest.py` — and `filterwarnings = ["error"]`
(pinned, non-negotiable per `backend-stack.md`) turns either one into a
collection-time `SystemExit`-equivalent failure of the *entire* suite, before
a single test runs. Neither warning is caused by any application code in this
step.

Fix landed in `backend/pyproject.toml`:

- `httpx2>=2.12.0` added to `[dependency-groups] dev`, alongside the spec's
  pinned `pytest`/`httpx`/`ruff` trio (not a replacement for `httpx`, which
  stays — some other tooling may still expect it importable).
- `[tool.uv] constraint-dependencies = ["anyio<4.15"]` — a transitive-only
  constraint (`anyio` is not, and must not become, a direct dependency); it
  keeps `uv.lock` off the first `anyio` release that deprecated the alias
  Starlette 1.6.0 still uses internally.

Verified: `import warnings; warnings.simplefilter("error"); from fastapi.testclient
import TestClient` is clean with both changes in place and reproducibly fails
with either one reverted. This is an environment-resolution fix, not a
change to any pinned wire contract, route, or service signature — flagged
here because it affects every future step's `uv.lock` regeneration: **do not
drop `httpx2` or loosen the `anyio` constraint** without re-verifying this
import stays clean under `filterwarnings = ["error"]`.

### D36 — `TestClient(...).get/post(url, cookies={...})` is unusable under `filterwarnings = ["error"]`; use a `Cookie` header instead

Found during qa-backend's mode-B verification of step 0.1: with `httpx>=0.28.1`
(pinned floor, §6.1) — and identically with the `httpx2` dev dependency of D31
installed, since Starlette 1.6.0's `TestClient` prefers it when present — the
per-request `cookies=` parameter on `Client.request()` is itself deprecated
and emits `warnings.warn(..., DeprecationWarning, stacklevel=2)` on every
call, independent of D31's import-time warning and not fixed by it. Under the
pinned `filterwarnings = ["error"]` this fails any test that calls
`client.get(path, cookies={...})` or `client.post(path, cookies={...})`, which
is otherwise the obvious way to simulate a specific (possibly stale) session
cookie against a shared `client` fixture — exactly the pattern this suite's
auth tests need. Fixed in `backend/tests/**` (qa-backend's own tree, no
`app/` change needed): `tests/conftest.py` gained a `session_cookie_header`
fixture returning `{"Cookie": f"session={token}"}`, and every call site that
previously passed `cookies={"session": ...}` now passes that as (part of) its
`headers=` instead — verified clean by direct inspection of both `httpx` and
`httpx2`'s `Client.request()` source, which special-case `cookies=` for the
warning but forward `headers=` untouched. A later step's tests must keep
using `session_cookie_header` (or the same `Cookie`-header pattern) rather
than reintroducing `cookies=` on a `TestClient` call.

### D38 — Primary keys and foreign keys are ULIDs, not UUIDs: `app/core/ids.py`

Every model's id column is a 26-character Crockford base32 ULID string,
stored as `CHAR(26)` (not `postgresql.UUID`), and is a plain `str` in Python
and on the wire — no `uuid.UUID` anywhere in `app/`. The primitive lives in
`app/core/ids.py` (a `users`+`sessions` two-caller case, hence `core/`):

```python
from app.core.ids import ID_TYPE, generate_id
id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
user_id: Mapped[str] = mapped_column(ID_TYPE, ForeignKey("users.id", ondelete="CASCADE"), ...)
```

`ID_TYPE` is `sqlalchemy.CHAR(26)`; `generate_id()` returns `str(ULID())` from
the `python-ulid` package (`from ulid import ULID`), pinned
`python-ulid>=3.1.0` in `pyproject.toml` (resolved to `4.0.1` at lock time).
Every new model's PK/FK declares its column through `ID_TYPE` +
`generate_id` — there is no second way to declare an id. Pydantic schemas
type the field `str` (e.g. `UserRead.id: str`), not `uuid.UUID`.

The baseline migration (`0001_baseline.py`) was edited in place (not
stacked) to create `CHAR(26)` columns directly, since no production data
exists; revision id, constraint names and `downgrade()` are unchanged.
Verified with a real Postgres instance: `alembic upgrade head` →
`downgrade -1` → `upgrade head` round-trips cleanly, `information_schema`
confirms `character(26)` on `users.id`, `sessions.id`, `sessions.user_id`,
and a live `POST /api/v1/auth/register` through `TestClient` returns a
26-character ULID as `id`. `frontend/openapi.json` and
`frontend/src/api/schema.d.ts` were regenerated accordingly (no `format:
uuid` remains). Test fixtures build ids with `generate_id()` too —
`tests/factories.py` defaults both `make_user` and `make_session` to it, so a
test needing an id calls `generate_id()` rather than writing a literal.

### D37 — The failed-sign-in log event's name is `sign_in_failed`

D25 pinned the level (`INFO`) and the payload (the submitted username) but not
an event name. Landed in `app/modules/auth/routes.py::sign_in`: on the
`INVALID_CREDENTIALS` branch (which covers both the unknown-username and the
wrong-password cases identically, since `users_service.verify_credentials`
collapses both to `None`), the route calls
`logger.info("sign_in_failed", username=payload.username)` — a module-level
`logger = structlog.get_logger()` in that file, the same pattern
`core/errors.py` already uses for `unhandled_exception` — before raising
`ApiError(ErrorCode.INVALID_CREDENTIALS)`. No new logging path: this goes
through the existing `structlog` configuration in `core/logging.py`
(`PrintLoggerFactory(sys.stderr)`), so it lands on stderr and `stdout` stays
pure JSON for `app openapi export`. The dummy Argon2 verify inside
`verify_credentials` (timing parity for the unknown-username branch) is
untouched. A later step asserting on this event should match on
`event="sign_in_failed"` and the `username` field.
