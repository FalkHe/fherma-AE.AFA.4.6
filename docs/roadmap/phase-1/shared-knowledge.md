# Phase 1 — Shared Knowledge (binding contract)

This document is the **single source of truth** for every Phase-1 step. Every
agent working on a Phase-1 step must read it fully before writing code. When a
step file and this document disagree, this document wins. Do not deviate from
anything pinned here — if a deviation seems necessary, stop and report it
instead of improvising, because a parallel agent is building against the same
contract.

UI layout/state details live in [`ui-spec.md`](ui-spec.md) (binding for
frontend steps).

---

## Parallel-run rule

Two tracks run **concurrently**. Backend agents never touch `frontend/`;
frontend agents never touch `backend/`.

```text
backend-dev:   1.1 ──► 1.3 ──► 1.5
                         │
frontend-dev:  1.2 ──► 1.4 ──► 1.6
```

The **only cross-track sync point**: step 1.6 starts only after 1.3 is merged
(its first action is `pnpm generate:api`). Steps 1.2/1.4 build against the
stub rule below and require zero backend code.

---

## Auth API contract — final

All `/auth/*` endpoints are **plain JSON, exempt from JSON:API** (per
`docs/architecture.md`). The router mounts at `/auth` (no `/api` prefix). JSON
attributes are camelCase: Pydantic request/response models use
`alias_generator=to_camel, populate_by_name=True` while Python stays
snake_case.

**`UserResponse`** (shared response body):

```json
{"id": "<26-char ULID>", "username": "<string>", "role": "user" | "admin"}
```

| Endpoint | Request body | Success | Errors |
|---|---|---|---|
| `POST /auth/register` | `{"username": str, "password": str}` | `201` + `UserResponse`. Does **not** create a session — the SPA chains a login call. | `409 {"detail": "Username is already taken."}`; `422` FastAPI default validation shape |
| `POST /auth/login` | `{"username": str, "password": str, "rememberMe": bool}` (`rememberMe` optional, default `false`) | `200` + `UserResponse` + `Set-Cookie: session=…` + `Set-Cookie: csrf_token=…` | `401 {"detail": "Invalid username or password."}`; `422` default shape |
| `POST /auth/logout` | empty; requires session cookie + `X-CSRF-Token` header | `204`; deletes the session row; clears both cookies (`Max-Age=0`) | `401` no/expired session; `403 {"detail": "CSRF token missing or invalid."}` |
| `GET /auth/me` | — | `200` + `UserResponse` (role read **fresh from the DB** on every request) | `401 {"detail": "Not authenticated."}` |

Error bodies for `/auth/*` are always `{"detail": "<English sentence>"}`
(FastAPI convention). The frontend branches on **status code** (401/403/409),
never on the detail string, and shows its own i18n message.

---

## Cookies & CSRF — final

- **`session` cookie**: value = raw opaque token from
  `secrets.token_urlsafe(32)`. Attributes: `HttpOnly; SameSite=Lax; Path=/`;
  `Secure` iff `settings.environment == "production"`. With `rememberMe`:
  `Max-Age=2592000` (30 days). Without: **no Max-Age** (browser-session
  cookie).
- **Server-side expiry is authoritative and fixed — no sliding expiration,
  ever.** `SESSION_TTL = timedelta(hours=24)` without remember-me,
  `REMEMBER_ME_TTL = timedelta(days=30)` with; module constants in
  `session_service.py`. Expired sessions are deleted lazily on resolve; no
  scheduled cleanup.
- **`csrf_token` cookie**: fresh `secrets.token_urlsafe(32)` per login.
  **Not** HttpOnly (the SPA must read it); `SameSite=Lax; Path=/`; `Secure`
  same rule; same Max-Age policy as the session cookie. Not stored
  server-side.
- **Double-submit pattern**: a FastAPI dependency `csrf_protect` rejects (403)
  any cookie-authenticated unsafe request (`POST/PUT/PATCH/DELETE`) whose
  `X-CSRF-Token` header doesn't match the `csrf_token` cookie, compared with
  `secrets.compare_digest`. `login`/`register` are exempt (no session yet);
  `logout` and every future authenticated write require it. CSRF header name:
  **`X-CSRF-Token`**.
- Do not weaken `SameSite=Lax` or switch to header auth later — Phase-2
  `EventSource` can only authenticate via this cookie.

---

## Validation rules — final

- **Username**: normalize with `username.strip().lower()` on **both write and
  lookup**; only the normalized form is stored. After normalization: 3–32
  chars matching `^[a-z0-9_.-]+$` (input may contain uppercase; it is folded,
  not rejected). Case-insensitive uniqueness therefore reduces to a plain
  unique index on the stored lowercase value.
- **Password**: min 8, max 128 chars; no other policy (strict password policy
  is explicitly out of scope per `docs/architecture.md`).
- **Both constraints apply at registration only.** `POST /auth/login` performs
  the username normalisation (`strip().lower()`, the service looks up the
  normalised form) but **no format or length validation**: login is a
  credential check, not data entry, so a syntactically impossible credential
  simply fails authentication with `401 {"detail": "Invalid username or
  password."}` on the usual constant-time path. Login still returns the
  default `422` for a missing field or a wrong JSON type.

---

## DB schema — final

ULID string PKs via the existing `ULIDPrimaryKeyMixin`
(`backend/app/db/models/base.py`; `String(26)`, app-generated). All
timestamps `TIMESTAMPTZ`, UTC. Constraint/index names come from the existing
naming convention on `Base.metadata`.

**`users`**
| Column | Type / constraint |
|---|---|
| `id` | `String(26)` PK (ULID mixin) |
| `username` | `String(32) NOT NULL`, unique (`uq_users_username`), stored lowercase |
| `password_hash` | `String(255) NOT NULL` |
| `role` | native PG enum `user_role('user','admin') NOT NULL`, server default `'user'` |
| `created_at` | `TIMESTAMPTZ NOT NULL`, server default `now()` |
| `updated_at` | `TIMESTAMPTZ NOT NULL`, server default `now()`, `onupdate now()` |

**`sessions`**
| Column | Type / constraint |
|---|---|
| `id` | `String(26)` PK (ULID mixin) |
| `user_id` | `String(26) NOT NULL` FK → `users.id ON DELETE CASCADE`, index `ix_sessions_user_id` |
| `token_hash` | `String(64) NOT NULL`, unique (`uq_sessions_token_hash`) |
| `remember_me` | `BOOLEAN NOT NULL DEFAULT false` |
| `expires_at` | `TIMESTAMPTZ NOT NULL` |
| `created_at` | `TIMESTAMPTZ NOT NULL`, server default `now()` |

**Session tokens are stored only as
`hashlib.sha256(raw_token.encode()).hexdigest()`** (64 hex chars); the cookie
carries the raw token; lookup is by hash. Never store the raw token —
retrofitting later invalidates all sessions.

---

## Backend conventions — final

- Password hashing: **pwdlib with Argon2** —
  `PasswordHash((Argon2Hasher(),))`. Dependency: `pwdlib[argon2]`.
- **Constant-time login**: module-level `_DUMMY_HASH` computed once at import
  (`password_hash.hash("dummy-password-for-timing")`); when the username
  doesn't exist, `authenticate` verifies the supplied password against
  `_DUMMY_HASH` and still returns `None`.
- Layering: route → service → SQLAlchemy; **services own transactions**
  (`session.commit()` in the service, never in routes or CLI). DB session via
  the existing `app/db/session.py` (`get_db_session` dependency for routes;
  the sessionmaker directly for CLI).
- Dependencies in `backend/app/api/deps.py`:
  - `current_user` — resolves the `session` cookie → **401** when
    absent/invalid/expired; loads the user row fresh so role changes apply to
    live sessions. Default guard for all future `/api/*` routers.
  - `current_admin` — builds on `current_user`; **403**
    `{"detail": "Admin privileges required."}` when `role != "admin"`.
    401 = not signed in; 403 = signed in, insufficient role.
  - `csrf_protect` — double-submit check as pinned above.
- `/health` and `/ready` stay **outside** all auth dependencies (Compose
  health checks break otherwise).
- **Sessions are revoked** (all rows for the user) on: password reset, and
  role change **admin → user** (demotion). Promotion does not revoke.
- **CLI async pattern** (canonical for every future async CLI command): the
  Typer command body is sync and calls `asyncio.run(_impl(...))`; `_impl`
  opens a session from the sessionmaker and calls the service. No SQL in the
  CLI layer. Passwords are prompted with
  `typer.prompt(..., hide_input=True, confirmation_prompt=True)` — never a
  CLI argument (shell history). Exit 0 on success (idempotent success
  included); exit 1 + stderr message on unknown username.

---

## Frontend conventions — final

- **File placement follows the landed Phase-0 convention** (route-level
  components in `routes/` with a `*Route.tsx` suffix, shared components in
  `components/`, hooks in `hooks/`):
  - `frontend/src/routes/LoginRoute.tsx`, `frontend/src/routes/RegisterRoute.tsx`
  - `frontend/src/routes/RequireAuth.tsx`, `frontend/src/routes/RequireAdmin.tsx`
  - `frontend/src/routes/admin/AdminHomeRoute.tsx`
  - `frontend/src/components/AdminLayout.tsx` (AppLayout stays at
    `frontend/src/components/AppLayout.tsx` — no `layouts/` directory, no
    file moves)
  - `frontend/src/hooks/useAuth.ts` (exports `useAuth`, `useLogin`,
    `useRegister`, `useLogout`)
- `useAuth()` shape:
  `{ user: {id, username, role} | null, isLoading: boolean, isAuthenticated: boolean }`,
  backed by TanStack Query key `["auth", "me"]`, `retry: false`,
  `staleTime: 5 * 60_000`; a 401 from `/auth/me` resolves to `user: null`
  (not an error state).
- **Route table** (React Router v7 — package `react-router`, not
  `react-router-dom`). One `AppLayout` wraps everything so the AppBar +
  theme toggle stay visible on the auth pages; `AppLayout` renders its
  account UI and nav only when `useAuth().user` exists:

  ```tsx
  <Routes>
    <Route element={<AppLayout />}>
      <Route path="login" element={<LoginRoute />} />
      <Route path="register" element={<RegisterRoute />} />
      <Route element={<RequireAuth />}>
        <Route index element={<HomeRoute />} />
        <Route element={<RequireAdmin />}>
          <Route path="admin" element={<AdminLayout />}>
            <Route index element={<AdminHomeRoute />} />
          </Route>
        </Route>
      </Route>
    </Route>
  </Routes>
  ```

- Guard behavior: while `isLoading`, render a centered MUI
  `CircularProgress` (exact spec in `ui-spec.md` §3) — never flash a
  redirect. `RequireAuth`:
  `<Navigate to="/login" state={{ from: location }} replace />`.
  `RequireAdmin`: non-admins → `<Navigate to="/" replace />` (no 403 page —
  the backend `current_admin` is the real boundary; **SPA guards are UX
  only**, every admin API endpoint must use `current_admin`).
- Login success navigates to `location.state?.from?.pathname ?? "/"`
  (redirect-preserving gate). Register success chains an automatic login with
  the same credentials (`rememberMe: false`), then navigates the same way.
  Logout: `POST /auth/logout` → `queryClient.clear()` → navigate `/login`.
- API client middleware (`frontend/src/api/client.ts`):
  `credentials: "include"` is already set (Phase 0). Step 1.6 adds:
  **onRequest** — for methods outside `{GET, HEAD, OPTIONS}`, read the
  `csrf_token` cookie from `document.cookie` and set `X-CSRF-Token`;
  **onResponse** — on 401 from any non-`/auth/` path,
  `queryClient.setQueryData(["auth", "me"], null)` (RequireAuth then
  redirects). The `QueryClient` instance moves to
  `frontend/src/queryClient.ts` so the middleware can import it.
- Forms: **plain controlled MUI inputs** — no React Hook Form/Zod at this
  size. Client-side checks mirror the pinned validation rules; server errors
  render by status code (mapping in `ui-spec.md`). **Every string goes
  through react-i18next** — key list in `ui-spec.md` §6, merged into
  `frontend/src/locales/en/translation.json`.
- **Stub rule (steps 1.2/1.4 only)**: until step 1.6, `useAuth.ts` contains a
  clearly marked stub:

  ```ts
  // STUB — replaced wholesale in step 1.6. Shape is pinned by
  // docs/roadmap/phase-1/shared-knowledge.md; do not change it.
  const STUB_USER = { id: "0".repeat(26), username: "dev", role: "user" as const };
  ```

  `useAuth` returns `{ user: STUB_USER, isLoading: false, isAuthenticated: true }`
  synchronously; `useLogin`/`useRegister`/`useLogout` are async no-ops with
  the same call signatures as the real hooks. Step 1.6 deletes the stub
  wholesale — components written against it need no changes in 1.6.
  Consequence: the "already-authenticated users are redirected away from
  `/login`/`/register`" behavior is **implemented in step 1.6, not 1.2**
  (with the stub it would make the auth pages unreachable in dev).

---

## Landed decisions

Appended by implementing agents when a step finishes — decisions later steps
depend on. 1–3 bullets per step, no prose.

### Step 1.1 (auth data model & services)

- Services are **module-level functions** (no classes), taking `AsyncSession`
  as the first parameter — imitate `app/services/user_service.py` /
  `session_service.py`.
- Transaction ownership: `revoke_all_for_user` **commits**;
  `delete_all_for_user` deliberately **does not commit** — callers own the
  transaction so demotion/reset stay single-transaction.
- ORM models define **no relationships** (avoids async lazy-load traps); the
  `UserRole` native enum uses `values_callable` so lowercase values are stored.

### Step 1.2 (auth screens, UI-only)

- `hooks/useAuth.ts` exports the types `AuthUser`, `LoginInput`
  (`{username, password, rememberMe}`), `RegisterInput` (`{username, password}`)
  and returns **real `useMutation` results** (`UseMutationResult<AuthUser, Error, …>`;
  logout `<void, Error, void>`) — step 1.6 replaces only the `mutationFn`, so
  `isPending`/`mutate`/`mutateAsync` usage in components stays valid. Step 1.6
  must re-export the same type names or update both routes.
- Contract for 1.6: the register→login chain lives **inside `useRegister`**
  (hence it resolves to the authenticated `AuthUser`, not the created one);
  `["auth","me"]` invalidation belongs in the hooks, `navigate()` and the
  status-code→message mapping belong in the routes. Both routes already hold
  the general-error slot as local state typed to `auth.errors.*` keys
  (`GeneralErrorKey`), cleared at the start of every submit.
- Deliberate omissions left for 1.6, per the step's out-of-scope list: no
  navigation on success, no `Navigate`-away-when-authenticated, no username ref
  on `LoginRoute` (register has refs for first-invalid-field focus). Per
  ui-spec §1 login does **no** client-side validation beyond `required`; only
  `RegisterRoute` mirrors the pinned username/password rules (on submit only).

### Step 1.3 (auth endpoints, cookies & CSRF)

- `app/api/deps.py` exports `current_user`, `current_admin`, `csrf_protect` plus
  `SESSION_COOKIE_NAME` / `CSRF_COOKIE_NAME` / `CSRF_HEADER_NAME`; the session
  cookie and the CSRF header are read from `Request`, **not** declared as
  `Cookie`/`Header` params, so they never appear in the OpenAPI schema (no
  cookie/header args in the generated client). Later routers: `Depends(current_user)`
  (or `current_admin`) plus `Depends(csrf_protect)` on every write.
- Cookie attributes live in `app/api/endpoints/auth.py` (`COOKIE_PATH`,
  `COOKIE_SAMESITE="Lax"`, `REMEMBER_ME_MAX_AGE` derived from
  `session_service.REMEMBER_ME_TTL`); `_set_auth_cookies` / `_clear_auth_cookies`
  are the only places that touch them. Verified wire form in development:
  `session=…; HttpOnly; Max-Age=2592000; Path=/; SameSite=Lax` (no `Max-Age`
  without `rememberMe`, no `Secure` outside production).
- Validation lives in `app/api/schemas/auth.py` on a private `_CredentialsRequest`
  base (`@field_validator`, so 422s carry `loc: ["body","username"|"password"]`);
  the username validator normalises (`strip().lower()`) before checking, so
  `payload.username` reaching the service is already normalised. `_CredentialsRequest`
  is not exported in OpenAPI — only `RegisterRequest`, `LoginRequest`, `UserResponse`.
  `api/schemas/__init__.py` and `api/endpoints/__init__.py` stay pure package
  markers (no re-exports, as with `health`).

### Step 1.4 (route guards & admin shell, UI-only)

- The ui-spec §3 spinner lives in **one** exported component,
  `GuardSpinner` in `routes/RequireAuth.tsx`, imported by `RequireAdmin` — every
  later guarded route reuses it, never its own loading UI. Both guards branch on
  `useAuth().isLoading` only (first fetch, no cached data), so 1.6 must not
  surface `isFetching` through that field or background refetches will blank
  guarded pages.
- `AppLayout` sign-out currently only calls `logout.mutate()` + closes the menu
  (deliberate no-op per the step's out-of-scope list). Step 1.6 adds
  `queryClient.clear()` + `navigate("/login", { replace: true })` on settle at
  the marked comment in `handleSignOut`; nav/account blocks already render on
  `user !== null`, so nothing else in the layout changes.
- Icons follow the landed Material Symbols convention (`<Icon>ligature</Icon>`,
  as in `ThemeModeToggle`) — `@mui/icons-material` is **not** a dependency; use
  `account_circle` / `arrow_drop_down` / `logout` / `pending_actions`.
  `AdminLayout` derives the selected tab from the `tabValueByPath` map (`false`
  when unmatched). ~~Phase 2 adds `"/admin/review": "review"` there.~~
  *Superseded by the Phase-2 ui-spec: no second admin tab — review is a
  drill-down at `/admin/models/:id`; the derivation loosens to
  `startsWith("/admin") → "backlog"` (Phase-2 step 2.8).*

### Step 1.5 (CLI user commands & bootstrap docs)

- `app/cli/users.py` is the landed reference for the CLI async pattern: sync
  Typer body → `asyncio.run(_impl(...))`, one `async with get_sessionmaker()()`
  per `_impl`, service call inside (the service commits). No engine `dispose()`
  is needed — verified: no loop/connection warnings on exit; don't add one.
- CLI error convention: service exceptions are caught in the **sync** body and
  funnelled through a `-> NoReturn` helper that writes the message to stderr
  (`typer.echo(..., err=True)`) and raises `typer.Exit(code=1)`; success
  messages go to stdout. Enum arguments use the ORM enum directly (`UserRole`,
  a `StrEnum`) — Typer renders `<user|admin>` and rejects other values itself
  (exit 2).
- CLI commands do **not** re-validate input (no password length check):
  validation stays at the API boundary and normalisation in the service, so the
  raw username string is passed through unchanged.

### Step 1.6 (frontend auth wiring)

- `hooks/useAuth.ts` now aliases the generated types (`AuthUser`/`LoginInput`/
  `RegisterInput` = `components["schemas"]["UserResponse"|"LoginRequest"|"RegisterRequest"]`)
  and adds one export, `AuthError` (`status`, plus `validationFields` parsed from
  a 422 body). Screens branch on `error instanceof AuthError && error.status === …`
  — never on the `detail` sentence; that is the pattern for every future
  status-code mapping.
- `src/queryClient.ts` holds the single `QueryClient`; it is imported **only** by
  `api/client.ts` (middleware runs outside React) — hooks and components use
  `useQueryClient()`. The middleware sets `X-CSRF-Token` on every method outside
  `{GET, HEAD, OPTIONS}` and writes `null` into `["auth","me"]` on a 401 from any
  non-`/auth/` path, so no call site handles CSRF or session expiry itself.
- `useLogout` treats 401 as success and clears the cache in `onSuccess`; the
  caller navigates from its own mutate-level `onSuccess` (`AppLayout`), so a
  403/5xx leaves the user in place. On both auth screens the
  authenticated-redirect is gated `user !== null && !mutation.isSuccess` —
  without that gate the cache write from a fresh login re-renders the screen and
  its `<Navigate to="/">` beats the redirect-preserving `navigate(from)`. Reuse
  the gate for any future public-only route.
- **Disabled-while-pending focus trap** (applies to every form that disables its
  inputs during a mutation): a mutation's `onError` runs *before* React commits
  the error render, so the field is still `disabled` and browsers silently ignore
  `focus()` on it. Programmatic refocus therefore belongs in a `useEffect` keyed
  on **both** the error state and `!isPending` — never in the mutation callback.
  `routes/LoginRoute.test.tsx` is the landed guard; note it must opt out of
  `act()` (`IS_REACT_ACT_ENVIRONMENT = false`), delay the stubbed response and
  make jsdom's `focus()` respect `disabled`, or it passes against the bug.

### Post-1.6 adjustment (login validation dropped — user-approved)

- **Login no longer validates credential format** (user decision): a 7-char
  password or a 2-char/invalid-pattern username used to return 422, which the
  SPA rendered as a generic server error instead of "invalid credentials".
  `LoginRequest` now only normalises the username; the length/pattern checks
  moved onto `RegisterRequest`, whose behaviour is unchanged.
- Structure in `app/api/schemas/auth.py`: `_CredentialsRequest` holds
  `username`/`password` plus the `normalize_username` validator only;
  `RegisterRequest` adds `check_username_format` + `check_password_length`.
  **Validator order is load-bearing** — the inherited normaliser runs before
  the subclass format check, so `"  Alice  "` is folded, not rejected
  (`test_register_username_is_stripped_and_lowercased` guards it).
- The validators are `@field_validator`s, so they never appeared as
  `minLength`/`maxLength`/`pattern` in OpenAPI: the exported schema changed
  only in the two models' `description` strings and no client regeneration is
  needed. Any future endpoint wanting machine-readable constraints must use
  `Field(...)` instead.
