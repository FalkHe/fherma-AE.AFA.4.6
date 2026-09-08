---
title: "Step 0.1 — Scaffolding, authentication, blank home page"
phase: 0
status: spec
created: 2026-09-08
---

# Step 0.1 — Scaffolding, authentication, blank home page

Foundation slice. `backend/` and `frontend/` do not exist; this step creates
both, boots them under the existing Docker environment, and delivers exactly
one working feature: username/password authentication with a single
authenticated page that says hello.

Read together with [`shared-knowledge.md`](shared-knowledge.md) (binding phase
contract), [`../../general/architecture.md`](../../general/architecture.md),
[`../../general/backend-stack.md`](../../general/backend-stack.md) and
[`../../general/frontend-stack.md`](../../general/frontend-stack.md).

## 1. Scope

In scope:

- Backend skeleton that boots under `docker/entrypoint-web.sh`
  (`alembic upgrade head`, then `uvicorn app.main:create_app --factory`).
- Backend `health`, `users` and `auth` modules.
- Alembic tree with one baseline migration.
- Typer CLI registered as the console script `app`, with `app openapi export`
  (required by `make generate-api`).
- Frontend skeleton that boots under `docker/frontend.Dockerfile`
  (`pnpm run dev`, Vite on `0.0.0.0:5173`).
- Frontend `auth` and `home` modules: sign-up form, sign-in form, sign-out,
  route protection, one greeting page.
- The ESLint/typecheck/test scripts in `package.json` (the `src/test/`
  helpers themselves are qa-frontend's — §6.6).

- `frontend/src/modules/home/components/AppShell.tsx` — the app frame that
  later phases extend (`ui-spec.md` §3). `src/components/` is **empty** in
  phase 0 (§6.3 R2, `shared-knowledge.md` D1).

Out of scope — do not add, not even as a stub: game content, dice, SRD, RAG,
vector columns, pgvector extension, LangChain, LangGraph, OpenRouter calls,
Langfuse wiring, background jobs, Redis, roles/permissions beyond a single
implicit `user`, password reset, email, rate limiting, a language switcher, a
dark-mode toggle.

"Nothing else on it" governs the home page's **content**: a greeting and a way
to sign out, and no dashboard, cards, lists or coming-soon teasers. It does not
forbid the shell that holds it — see §6.3 R2.

## 2. Environment facts the implementation must satisfy

These come from files neither dev agent may edit.

| Fact | Source |
|---|---|
| `alembic upgrade head` runs with CWD `/app` before uvicorn | `docker/entrypoint-web.sh` |
| App factory is `app.main:create_app` | `docker/entrypoint-web.sh` |
| `backend/pyproject.toml`, `backend/uv.lock`, `backend/.python-version` must all exist | `docker/backend.Dockerfile` |
| Python 3.12, uv 0.11, venv at `/opt/venv` | `docker/backend.Dockerfile` |
| `frontend/package.json`, `frontend/pnpm-lock.yaml`, `frontend/pnpm-workspace.yaml` must all exist | `docker/frontend.Dockerfile` |
| Node 24, pnpm 11.17.0 (must match the `packageManager` field) | `docker/frontend.Dockerfile` |
| `pnpm run dev` must serve on `0.0.0.0:5173` | `docker/frontend.Dockerfile`, `compose.yaml` |
| `VITE_API_URL=http://localhost:8000`, `VITE_SERVER_USE_POLLING=true` | `compose.yaml` |
| `make generate-api` runs `app openapi export` inside `app-web` and redirects **stdout** to `frontend/openapi.json` | `Makefile` |
| `make backend-test` runs bare `pytest` in `app-cli` with CWD `/app` | `Makefile` |
| `make frontend-test` / `-lint` / `-typecheck` run `pnpm test` / `pnpm lint` / `pnpm typecheck` | `Makefile` |
| Postgres credentials `app:app@postgres:5432/application` | `compose.yaml` |

## 3. Settings

`backend/app/core/settings.py` declares **only** what step 0.1 uses. Extra
environment variables present in `.env` are ignored (`extra="ignore"` on
`SettingsConfigDict`), so the Langfuse and model keys in `.env.dist` do not
need to be declared and must not be.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `environment` | `Literal["development", "production"]` | `"development"` | Enables `/docs`; controls the `Secure` cookie flag and the log renderer |
| `log_level` | `str` | `"INFO"` | structlog / stdlib level |
| `database_url` | `str` | *required* | Async SQLAlchemy URL, used by the app and by Alembic |
| `session_ttl_seconds` | `int` | `1209600` | Session lifetime and cookie `Max-Age` |
| `frontend_origin` | `str` | `"http://localhost:5173"` | The single allowed CORS origin |

Accessor: `@lru_cache def get_settings() -> Settings`. Env var names are the
upper-case field names. `SettingsConfigDict(env_file=".env", extra="ignore")`.

Those five are the **complete** declared set — no sixth field, and none of the
model or Langfuse keys. `extra="ignore"` is what lets those undeclared keys sit
in `.env.dist` harmlessly: Compose passes the whole `.env` to `app-web`, and an
undeclared key must not be an error.

### `.env.dist` and `README.md` — already applied by the owner

Both files are settled; **dev agents must not touch either.** For the record:

1. `SESSION_SECRET` is gone. Nothing signs anything — session tokens are
   256-bit random values stored as SHA-256 hashes and looked up in the
   `sessions` table, and the CSRF token is a random value on the session row.
2. `SESSION_TTL_SECONDS=1209600` kept, now commented to say why there is no
   secret to configure.
3. `FRONTEND_ORIGIN=http://localhost:5173` added, commented as the
   credentialed-CORS origin matching the `frontend` service's published port.
4. The `LOG_LEVEL` comment now states that logs go to stderr because stdout
   must stay pure JSON for `app openapi export`.
5. The `README.md` quick-start line reads
   `cp .env.dist .env       # every default works out of the box` — so a fresh
   checkout boots with no editing.

## 4. Data model

Two tables, created by one baseline migration
(`backend/alembic/versions/0001_baseline.py`, `revision = "0001"`,
`down_revision = None`). Migration head after this step: **`0001`**.

### `users`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `UUID` | no | PK, `default=uuid.uuid4` generated in Python |
| `username` | `VARCHAR(32)` | no | Unique. Stored **lower-cased** |
| `password_hash` | `VARCHAR(255)` | no | Argon2 encoded hash |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | no | `server_default=func.now()` |

Indexes: `pk_users` (PK), `uq_users_username` (unique on `username`).

### `sessions`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `UUID` | no | PK, `default=uuid.uuid4` |
| `user_id` | `UUID` | no | FK → `users.id`, `ondelete="CASCADE"` |
| `token_hash` | `VARCHAR(64)` | no | Unique. Lower-case hex SHA-256 of the cookie token |
| `csrf_token` | `VARCHAR(64)` | no | Random value, stored in clear — it is not an authenticator on its own |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | no | `server_default=func.now()` |
| `expires_at` | `TIMESTAMP WITH TIME ZONE` | no | Set by the application to `now + session_ttl_seconds` |

Indexes: `pk_sessions` (PK), `uq_sessions_token_hash` (unique on `token_hash`),
`ix_sessions_user_id`.

The ORM class for `sessions` is named **`UserSession`** (never `Session` — that
name is taken by SQLAlchemy and by the request-scoped DB session).

There is no `role` column: there is one persona. There is no sliding
expiry, no `last_seen_at`, and no expired-session sweeper — this project has no
job runner. Expired rows accumulate; that is accepted for now and noted here so
a later step can add a CLI command for it.

Alembic up/down round-trip expectation: `alembic upgrade head` then
`alembic downgrade base` then `alembic upgrade head` must all succeed against a
fresh database. `downgrade()` drops `sessions` before `users`.

## 5. Wire contract

Base path `/api/v1`. All request and response bodies are JSON with
**camelCase** keys, produced by a shared Pydantic base
(`alias_generator=to_camel`, `populate_by_name=True`). FastAPI serialises
response models by alias, so responses are camelCase automatically.

### 5.1 Error envelope

Every non-2xx response from the application has exactly this body:

```json
{
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Username or password is incorrect.",
    "details": null
  }
}
```

`details` is `null` or a JSON object. The complete code table — these strings
are the contract; do not invent others in this step:

| Code | Status | Emitted when | `message` |
|---|---|---|---|
| `VALIDATION_ERROR` | 422 | Request body fails Pydantic validation | `Request validation failed.` |
| `NOT_AUTHENTICATED` | 401 | No `session` cookie on a protected route | `Authentication required.` |
| `SESSION_EXPIRED` | 401 | `session` cookie present but unknown or past `expires_at` | `Your session has expired. Please sign in again.` |
| `INVALID_CREDENTIALS` | 401 | Sign-in with an unknown username or a wrong password | `Username or password is incorrect.` |
| `CSRF_TOKEN_INVALID` | 403 | Session valid, `X-CSRF-Token` missing or not matching | `CSRF token missing or invalid.` |
| `USERNAME_TAKEN` | 409 | Register with a username that already exists | `That username is already taken.` |
| `NOT_FOUND` | 404 | Unknown route | `Resource not found.` |
| `METHOD_NOT_ALLOWED` | 405 | Known path, wrong method | `Method not allowed.` |
| `INTERNAL_ERROR` | 500 | Any unhandled exception | `An unexpected error occurred.` |

`VALIDATION_ERROR` sets
`details = {"fields": jsonable_encoder(exc.errors())}`; every other code sets
`details = null`. `INTERNAL_ERROR` never leaks the exception: the traceback is
logged, the body is the fixed message above.

Messages are English and server-side only. The frontend never displays them —
it maps `code` to an i18n key (§6.6).

### 5.2 `GET /api/v1/health`

Unauthenticated. No CSRF. Does not touch the database — it proves the process
booted, nothing more.

`200`:

```json
{ "status": "ok" }
```

### 5.3 `POST /api/v1/auth/register`

Unauthenticated. No CSRF (no session exists yet). Creates the user **and signs
them in** — one round trip, and the sign-up form lands on the home page.

Request:

```json
{ "username": "Aragorn", "password": "hunter-of-orcs" }
```

Validation: `username` 3–32 characters matching `^[A-Za-z0-9_-]+$`;
`password` 8–128 characters, no complexity rules. Both required.

`201` — response headers `Set-Cookie: session=…` (§5.7) and
`X-CSRF-Token: <token>`; body:

```json
{
  "id": "9f1c0b6a-6f7c-4a2f-9a3e-0b6d1c2e3f40",
  "username": "aragorn",
  "createdAt": "2026-09-08T12:34:56.789012+00:00"
}
```

`username` in the response is the stored, lower-cased form.
`createdAt` is an ISO-8601 instant with a UTC offset, exactly as Pydantic
serialises a timezone-aware `datetime`. Tests must assert it parses, not its
literal spelling.

`409 USERNAME_TAKEN` — comparison is case-insensitive, so `Aragorn` collides
with `aragorn`.
`422 VALIDATION_ERROR`.

### 5.4 `POST /api/v1/auth/sign-in`

Unauthenticated. No CSRF. Always creates a **new** session row; an existing
session cookie is ignored and simply replaced.

Request: same shape as register. Validation is deliberately looser —
`username` 1–32, `password` 1–128, **no pattern** — so a wrong-format username
yields `401 INVALID_CREDENTIALS`, not a 422 that tells the caller the username
could not exist.

`200` — `Set-Cookie: session=…`, `X-CSRF-Token: <token>`, body is the same
`UserRead` object as §5.3.

`401 INVALID_CREDENTIALS` for both an unknown username and a wrong password —
one code, one message, no enumeration signal. The unknown-username path still
performs an Argon2 verification against a fixed dummy hash so the two paths
take comparable time.

`422 VALIDATION_ERROR`.

### 5.5 `POST /api/v1/auth/sign-out`

Requires a valid session **and** a valid CSRF token. No request body.

`204` — no body. `Set-Cookie` clears the `session` cookie (same `Path`,
`SameSite`, `Secure` as when it was set). The session row is deleted.

`401 NOT_AUTHENTICATED` / `401 SESSION_EXPIRED` — checked **before** CSRF.
`403 CSRF_TOKEN_INVALID`.

### 5.6 `GET /api/v1/users/me`

Requires a valid session. No CSRF (it is a read).

`200` — the `UserRead` object of §5.3, plus response header
`X-CSRF-Token: <token>` carrying the current session's CSRF token. This is how
the SPA re-acquires the token after a page reload.

`401 NOT_AUTHENTICATED` when the `session` cookie is absent.
`401 SESSION_EXPIRED` when it is present but the session is unknown or past
`expires_at`; the `session` cookie is cleared (by the `ApiError` handler, §6.1).
No database write happens on this path — the stale row is left alone.

**The split between those two codes is load-bearing, and this is the pinned
reading of it:** a cookie that is present but resolves to nothing —
past `expires_at`, deleted by a sweeper, signed out in another tab, or simply
forged — is `SESSION_EXPIRED`, not `NOT_AUTHENTICATED`. The server cannot tell
those apart, and it does not try. `NOT_AUTHENTICATED` means, precisely, *no
cookie was sent*. The consequence is accepted knowingly: a visitor arriving
with a long-dead cookie is told their session ended, which is true from their
point of view, while a visitor with no cookie is told nothing. This is the
signal the SPA uses to decide whether to show the session-expired warning
(§6.3 R14), so it must not be blurred.

### 5.7 Session cookie

One cookie, no others.

| Attribute | Value |
|---|---|
| Name | `session` |
| Value | `secrets.token_urlsafe(32)` (43 URL-safe characters) |
| `HttpOnly` | yes |
| `Path` | `/` |
| `SameSite` | `Lax` |
| `Secure` | only when `environment == "production"` |
| `Max-Age` | `session_ttl_seconds` |
| `Domain` | not set (host-only) |

`SameSite=Lax` is correct even though the SPA is served from
`localhost:5173` and the API from `localhost:8000`: SameSite compares sites,
and the port is not part of a site. The request is nevertheless
**cross-origin**, so CORS and `credentials: "include"` are both mandatory
(§5.9, §6.2).

The database stores `sha256(token).hexdigest()`, never the token. A stolen
database dump therefore does not yield usable session cookies.

### 5.8 CSRF mechanism

Synchroniser token, delivered in a response header and never in a cookie.

- **Where it comes from**: `secrets.token_urlsafe(32)`, generated with the
  session and stored in `sessions.csrf_token`.
- **How the client gets it**: response header `X-CSRF-Token` on exactly three
  responses — `POST /auth/register` (201), `POST /auth/sign-in` (200),
  `GET /users/me` (200). No other response carries it.
- **How the client returns it**: request header `X-CSRF-Token`.
- **Which requests require it**: every request that (a) mutates state and (b)
  is authenticated by the `session` cookie. In step 0.1 that is exactly
  `POST /auth/sign-out`. `register` and `sign-in` are exempt: no session
  exists yet, so there is nothing to protect. This exemption is deliberate —
  login-CSRF is not a threat worth a pre-session handshake here.
- **How it is checked**: constant-time comparison of the header against
  `sessions.csrf_token` for the session that authenticated the request.
  Mismatch, empty or absent → `403 CSRF_TOKEN_INVALID`.

The token is never put in a cookie and never in a response body: an attacker's
cross-site page cannot read a CORS-protected response, so it cannot learn the
token. Because the header is compared against the row in the database rather
than against a second cookie, the classic double-submit cookie-injection
weakness does not apply.

### 5.9 CORS

`CORSMiddleware` with:

```python
allow_origins=[settings.frontend_origin]   # exactly one, never "*"
allow_credentials=True
allow_methods=["GET", "POST", "OPTIONS"]
allow_headers=["Content-Type", "X-CSRF-Token"]
expose_headers=["X-CSRF-Token"]
```

`expose_headers` is load-bearing: without it the browser hides
`X-CSRF-Token` from the SPA and every mutation fails with 403. Note that
Starlette adds `Access-Control-Expose-Headers` to *simple* responses only,
never to a preflight — criteria 29 and 30 are split along that line.

One known limitation, recorded in `shared-knowledge.md` D26 and not fixed
here: the catch-all `Exception` handler runs on `ServerErrorMiddleware`, which
sits outside `CORSMiddleware`, so a `500` reaches a browser without CORS
headers and the SPA sees a network failure rather than
`common:errors.unexpected`. The envelope on the wire is still correct.

## 6. Implementation contract

### 6.1 Backend layout and named surfaces

```
backend/
├── .python-version                 # 3.12
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/0001_baseline.py
└── app/
    ├── __init__.py
    ├── main.py                     # create_app()
    ├── cli.py                      # Typer app, exported as `cli`
    ├── core/
    │   ├── __init__.py
    │   ├── settings.py             # Settings, get_settings()
    │   ├── logging.py              # configure_logging()
    │   ├── db.py                   # Base, get_engine, get_sessionmaker, get_db_session, DbSession
    │   ├── errors.py               # ErrorCode, ApiError, register_error_handlers()
    │   ├── schemas.py              # CamelModel, ErrorBody, ErrorEnvelope
    │   └── security.py             # hash_password, verify_password, generate_token, hash_token, tokens_equal
    ├── api/
    │   ├── __init__.py
    │   └── v1/
    │       ├── __init__.py
    │       └── router.py           # api_router: combines module routers, nothing else
    └── modules/
        ├── __init__.py
        ├── health/{__init__.py, routes.py}
        ├── users/{__init__.py, models.py, schemas.py, routes.py, service.py}
        └── auth/{__init__.py, models.py, schemas.py, routes.py, service.py, dependencies.py}
```

`app/core/security.py` earns its place in `core/` because it has two module
callers: `users` (password hashing) and `auth` (token generation and
comparison). Nothing else goes in `core/` in this step.

`app/api/v1/router.py` exports `api_router: APIRouter` and does exactly this:
includes `health.routes.router` at prefix `/health` tag `health`,
`auth.routes.router` at `/auth` tag `auth`, `users.routes.router` at `/users`
tag `users`. `main.py` mounts it at `/api/v1`.

**Pinned service signatures.** These are the seam the backend test suite is
written against, so the names and shapes are contract, not suggestion.

```python
# app/modules/users/service.py
def normalize_username(raw: str) -> str                      # strip + lower-case
async def create_user(db: AsyncSession, *, username: str, password: str) -> User        # commits
async def get_user_by_username(db: AsyncSession, *, username: str) -> User | None
async def get_user_by_id(db: AsyncSession, *, user_id: UUID) -> User | None
async def verify_credentials(db: AsyncSession, *, username: str, password: str) -> User | None
```

`create_user` raises `ApiError(USERNAME_TAKEN)` when the username exists.
`verify_credentials` normalises the username, returns `None` on unknown user or
wrong password, and always runs one Argon2 verification.

```python
# app/modules/auth/service.py
@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    max_age: int

async def create_session(db: AsyncSession, *, user: User) -> IssuedSession   # commits
async def resolve_session(db: AsyncSession, *, token: str) -> UserSession | None
async def delete_session(db: AsyncSession, *, token: str) -> None            # commits
```

`resolve_session` returns `None` for an unknown token **and** for an expired
one, and performs no writes.

```python
# app/modules/auth/dependencies.py
@dataclass(frozen=True)
class AuthContext:
    user: User
    session: UserSession

async def require_auth(request: Request, db: DbSession) -> AuthContext
async def require_csrf(request: Request, auth: CurrentAuth) -> AuthContext

CurrentAuth = Annotated[AuthContext, Depends(require_auth)]
CsrfAuth = Annotated[AuthContext, Depends(require_csrf)]
```

`require_auth` performs **exactly two service calls, in this order** — there
is no ORM `relationship()` (`architecture.md`), so `UserSession` has no `.user`
attribute and the user is a second query:

1. `auth_service.resolve_session(db, token=<session cookie value>)` →
   `UserSession | None`. Absent cookie → `ApiError(NOT_AUTHENTICATED)` without
   calling this at all. `None` → `ApiError(SESSION_EXPIRED)`.
2. `users_service.get_user_by_id(db, user_id=session.user_id)` →
   `User | None`. `None` (an orphaned row) → `ApiError(SESSION_EXPIRED)`.

`AuthContext(user=<result of 2>, session=<result of 1>)`. qa-backend therefore
stubs **two** functions for any authenticated route, never one.
`require_csrf` makes no service call: it compares the header against
`auth.session.csrf_token`.

`require_auth` does **not** clear the cookie itself, and takes **no** `Response`
parameter — that is why the signature above has none. It raises `ApiError`, and
FastAPI discards a dependency's injected `Response` when the dependency raises,
so a `delete_cookie` there would never reach the client. See the cookie rule
below.

**How routes and dependencies call services — the test seam.** Monkeypatching
`app.modules.users.service.create_user` only works if the caller holds a
*module* reference, so:

- inside a module, `from . import service` and call `service.create_user(...)`;
- across modules, `from app.modules.users import service as users_service` and
  call `users_service.verify_credentials(...)` (the two-module case in `auth`,
  where a bare `service` name is already taken).

**Nothing imports a service function by name.** `from .service import
create_user` is a contract violation: it rebinds the function into the route
module and the monkeypatch of §6.5 silently misses.

**Cookies and headers — the one rule.** Routes and dependencies never
construct a `Response` and never return one. They take `response: Response` as
a parameter, call `response.set_cookie(...)` / `response.delete_cookie(...)` /
`response.headers[...] = ...` on it, and return the response **model** or
`None`; FastAPI merges those headers into the real response, including the
bodiless `204` of sign-out. Consequently:

- `register`, `sign_in` and `read_current_user` set `X-CSRF-Token` (and the
  first two the `session` cookie) on the injected `response`;
- `sign_out` is `async def sign_out(response: Response, auth: CsrfAuth) ->
  None` — it calls `response.delete_cookie(...)` and returns `None`. A bare
  `return Response(status_code=204)` is a contract violation: it bypasses the
  header merge and criterion 23 fails;
- the `SESSION_EXPIRED` cookie clearing is done **by the `ApiError` handler in
  `register_error_handlers`**, which — for that code only — deletes the
  `session` cookie on the `JSONResponse` it builds, using the §5.7 attributes
  (`path="/"`, `samesite="lax"`, `secure` only in production). That is the
  only place in the codebase that clears the cookie on a failure path, and it
  covers `/users/me`, sign-out and every later protected route at once.

**Pinned route function names** — the generated OpenAPI `operationId`s derive
from them, so changing one breaks the committed types:
`read_health`, `register`, `sign_in`, `sign_out`, `read_current_user`.

Route functions carry **no docstrings** and Pydantic fields carry no
`description=`, so the exported schema stays byte-stable against the committed
`frontend/openapi.json` (§7). Explanatory prose goes in a `#` comment above
the decorator.

**Pinned schema class names** (they become OpenAPI component names):
`ErrorBody`, `ErrorEnvelope`, `HealthRead`, `RegisterRequest`, `SignInRequest`,
`UserRead`.

Every route declares its failure responses explicitly so they reach the
schema, e.g. `responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}}`.
The status-code set per route is exactly the one in `frontend/openapi.json`.

**Transactions.** `get_db_session` yields a session and rolls back on
exception; it never commits. Service functions own the transaction boundary:
`create_user`, `create_session` and `delete_session` call
`await db.commit()`. Routes contain no `commit`, no `add`, no `execute`.

**Engine construction.** `get_engine()` and `get_sessionmaker()` are
`@lru_cache`d and must not be called at import time — not in `create_app()`,
not at module scope, not in a lifespan. There is no lifespan handler in this
step: nothing needs starting or stopping. This is what keeps the test suite
engine-free (§6.5).

**Logging.** `configure_logging()` sets up structlog writing to **stderr**:
`ConsoleRenderer` when `environment == "development"`, `JSONRenderer`
otherwise, level from `log_level`. Called once from `create_app()` and once
from the CLI entry point. Two log events exist in this step: a failed sign-in
at `INFO` with the submitted username (never the password), and the unhandled
exception at `ERROR` with the traceback.

The submitted username is the **only** user-supplied value that reaches a log
in this step. That is accepted (it is the field an operator needs to read a
credential-stuffing pattern) and recorded in `shared-knowledge.md` D25 so it is
not rediscovered as a leak.

`configure_logging()` must be **idempotent and re-callable**: structlog writes
to `sys.stderr`, which bypasses stdlib `logging`, so `caplog` sees nothing and
qa-backend asserts on `capsys` — which only captures output written *after*
pytest has replaced `sys.stderr`. It therefore calls `configure_logging()`
inside the test before exercising the failing route (criterion 28), and calling
it twice must not duplicate handlers or raise.

**CLI.** `app/cli.py` exposes `cli = typer.Typer()` with a sub-app `openapi`
providing one command, `export`, that prints
`json.dumps(create_app().openapi(), indent=2)` to stdout and nothing else.
`pyproject.toml` registers `[project.scripts] app = "app.cli:cli"`.

**`create_app()`** — in this order: `configure_logging()`, build
`FastAPI(title="AI Dungeon Master API", version="0.1.0")` with
`docs_url="/docs"`/`openapi_url="/openapi.json"` in development and both
`None` in production (`app.openapi()` keeps working either way), add
`CORSMiddleware` (§5.9), `register_error_handlers(app)`, then
`app.include_router(api_router, prefix="/api/v1")`.

**Alembic.** `alembic.ini` has `script_location = alembic`,
`prepend_sys_path = .`, `file_template = %%(rev)s_%%(slug)s`, and an empty
`sqlalchemy.url`; `env.py` takes the URL from `get_settings().database_url`,
runs online migrations through `create_async_engine` +
`connection.run_sync`, and imports every module's models explicitly for
`target_metadata = Base.metadata`:

```python
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.users import models as users_models  # noqa: F401
```

A new module adds one line here. No autodiscovery.

**Dependencies** (floors; `uv.lock` pins the resolution):
`fastapi>=0.141.1`, `uvicorn[standard]>=0.52.4`,
`sqlalchemy[asyncio]>=2.0.52`, `alembic>=1.19.2`, `pydantic>=2.13.5`,
`pydantic-settings>=2.15.0`, `psycopg[binary,pool]>=3.3.5`,
`typer>=0.27.2`, `argon2-cffi>=25.1.0`, `structlog>=26.1.0`.
Dev dependencies go in **`[dependency-groups] dev`**, never in
`[project.optional-dependencies]`: `uv sync --locked` in
`docker/backend.Dockerfile` installs the default dependency groups but no
extras, so as an extra `pytest` and `ruff` would be absent from the image and
criteria 6 and 7 would fail for a packaging reason. The group is
`pytest>=9.1.1`, `httpx>=0.28.1`, `ruff>=0.16.6`.
Build backend `hatchling` with `[tool.hatch.build.targets.wheel] packages = ["app"]`
(required: `uv sync --locked` installs the project, and `[project.scripts]`
needs a wheel). `requires-python = ">=3.12,<3.13"`.

`[tool.ruff]`: `line-length = 100`, `target-version = "py312"`,
`lint.select = ["E", "F", "I", "UP", "B", "SIM", "ASYNC"]`.
`[tool.pytest.ini_options]`: `testpaths = ["tests"]`,
`filterwarnings = ["error"]`, `addopts = "-q"`.

Argon2 uses `argon2.PasswordHasher()` with library defaults. No parameter
tuning, no rehash-on-verify.

### 6.2 Frontend layout and named surfaces

The screen design, component choice, every visual state, the copy, the i18n
keys, focus management and the a11y baseline are pinned by
[`ui-spec.md`](ui-spec.md), which is **binding alongside this file**. This
section pins only the file tree, the data-access surfaces and the routing
table; §6.3 records the small number of points where the two documents
conflicted and which one wins.

```
frontend/
├── package.json                    # "packageManager": "pnpm@11.17.0"
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── vite.config.ts
├── vitest.config.ts
├── eslint.config.js
├── index.html
├── openapi.json                    # committed by this spec; regenerated by make generate-api
└── src/
    ├── main.tsx                    # React root: the provider stack, nothing else
    ├── App.tsx                     # the route table, nothing else
    ├── api/schema.d.ts             # GENERATED — never hand-edited
    ├── core/
    │   ├── api/client.ts           # openapi-fetch client + CSRF middleware
    │   ├── api/errors.ts           # normalises any failure to { code, status }
    │   ├── i18n/index.ts
    │   ├── i18n/i18n.d.ts
    │   ├── i18n/locales/en/{common,auth,home}.json
    │   ├── queryClient.ts
    │   └── theme.ts
    ├── components/                  # EMPTY in phase 0 — see §6.3 R2
    ├── modules/
    │   ├── auth/
    │   │   ├── validation.ts       # USERNAME_MIN/MAX/PATTERN, PASSWORD_MIN/MAX + validators
    │   │   ├── components/AuthCard.tsx
    │   │   ├── components/SignInForm.tsx
    │   │   ├── components/SignUpForm.tsx
    │   │   ├── components/SignOutButton.tsx
    │   │   ├── components/RequireAuth.tsx
    │   │   ├── components/RequireAnonymous.tsx
    │   │   ├── hooks/useCurrentUser.ts
    │   │   ├── hooks/useSignIn.ts
    │   │   ├── hooks/useSignUp.ts
    │   │   ├── hooks/useSignOut.ts
    │   │   └── routes/{SignInRoute.tsx, SignUpRoute.tsx}
    │   └── home/
    │       ├── components/AppShell.tsx   # title + action slot + children; knows nothing of auth
    │       └── routes/HomeRoute.tsx
    └── test/{…}                     # qa-frontend's tree — see §6.6
```

`src/api/` is the one top-level directory outside the `core/ components/
modules/` scheme. It exists because the `Makefile` writes there, and it holds
generated artefacts only.

`src/components/` exists in the tree and is **empty** in phase 0.
`AppShell` lives at `modules/home/components/AppShell.tsx` because it has
exactly one caller: `/` is the only route that renders it, so `HomeRoute` is
that caller, and it is `HomeRoute` — not `modules/auth` — that imports
`SignOutButton` to fill the `action` slot. `modules/auth` never renders
`AppShell`. One module caller means D1's own rule applies: the file belongs to
its caller's module.

Its shape is unchanged and is still what makes it promotable: `title`, an
`action?: ReactNode` slot, `children`, and **no import from `modules/auth`**
(nor from any other module). The moment a **second** module renders it, it
graduates to `src/components/` unchanged. That is the expected path for shared
UI in this repo — born in its module, promoted on evidence — and it is recorded
as precedent in `shared-knowledge.md` D1 alongside the `AuthCard`
counter-example (two callers, both inside one module, so it stays put).

There is **no `modules/auth/api.ts`**: a per-module fetch layer with one caller
per function is a second HTTP client. The hooks call `api` from
`core/api/client.ts` directly and use `core/api/errors.ts` to normalise
failures. `core/api/errors.ts` sits in `core/` as a per-app singleton — the one
normalisation of the §5.1 envelope, alongside the client it normalises the
failures of — under D1's singleton exemption (criterion 43), not under the
"two module callers" bar. Its importers in phase 0 are the four `modules/auth`
hooks; `client.ts` does not import it.

`api/client.ts` exports:

```ts
export const api: Client<paths>          // openapi-fetch createClient
export function clearCsrfToken(): void
```

and owns the whole CSRF dance in one middleware: `onResponse` stores
`response.headers.get("X-CSRF-Token")` in a module-scoped `let` when present;
`onRequest` adds `X-CSRF-Token` to every non-`GET` request when a token is
held. `createClient` is configured with
`{ baseUrl: import.meta.env.VITE_API_URL, credentials: "include" }`. There is
**no `core/config.ts`**: one environment variable with one reader is not an
abstraction, and `client.ts` is the only file in `src/` that touches
`import.meta.env`. `credentials: "include"` is
mandatory — without it no cookie is sent and every authenticated request 401s.

The CSRF token lives in this module and nowhere else: no cookie reading, no
`localStorage`, no React state. It is re-acquired on every page load by
`useCurrentUser`.

`core/api/client.ts` has **that one job**. It holds no `QueryClient`
reference, writes nothing into the query cache, and contains no global `401`
interceptor — `createQueryClient()` is a factory and `core/api` has no way to
reach the instance anyway. Session expiry is handled where the state lives; see
§6.3 R10.

`queryClient.ts` exports a factory `createQueryClient()` with
`defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false, staleTime: 30_000 } }`.
`retry: false` matters: a 401 must resolve immediately, and the test suite must
not wait on retries.

`theme.ts` exports `theme = createTheme({ cssVariables: true, colorSchemes: {
light: true, dark: true } })` and nothing else — no `palette`, `typography` or
`components` override anywhere. `CssBaseline` is rendered **inside**
`ThemeProvider` (otherwise the scheme never reaches the page background); the
provider stack that does it is pinned below. Enabling the two schemes is not a
design decision: it costs one line and makes the app follow the operating
system instead of looking broken in dark mode.

**Provider composition — pinned, top to bottom.** `main.tsx` holds the whole
stack and nothing else; `App.tsx` holds `<Routes>` and nothing else. This is
the exact nesting, and the order is load-bearing (theme outermost so
`CssBaseline` covers everything; the router innermost so a test can substitute
a `MemoryRouter`). `noSsr` is the only prop besides `theme`: with two colour
schemes present `ThemeProvider` renders twice to guard SSR hydration, which a
Vite SPA never needs and which costs a dark-mode flicker.

```tsx
// src/main.tsx
const queryClient = createQueryClient();          // module scope: one instance

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider theme={theme} noSsr>
      <CssBaseline />
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </ThemeProvider>
  </StrictMode>,
);
```

`BrowserRouter` comes from `react-router/dom`; `Routes`, `Route`, `Navigate`,
`useNavigate` and `useLocation` come from `react-router` (v8 splits the two).

```tsx
// src/App.tsx — the whole file, modulo imports
export default function App() {
  return (
    <Routes>{/* the table below */}</Routes>
  );
}
```

**`App.tsx` contains no router and no provider.** That is what lets a test
render `<App />` inside a provider-supplying render helper without nesting two
routers — a nested router throws. Every provider in the stack above except
`BrowserRouter` is reproduced by that helper, which substitutes a
`MemoryRouter` (§6.6). A test that needs a specific starting location renders
`<App />` at that route; a test of one screen may render the route component
directly instead. Both are supported; nothing else mounts providers.

**Hooks contract.**

```ts
// The cached value, not just the user: the reason a read failed is part of the
// state the guard needs, and it comes from the server.
type CurrentUserState = { user: UserRead | null; sessionExpired: boolean }

useCurrentUser(): {                                   // queryKey ["currentUser"]
  user: UserRead | null
  sessionExpired: boolean
  isPending: boolean
  isError: boolean
  refetch: () => void
}
useSignUp(): UseMutationResult<UserRead, ApiFailure, { username: string; password: string }>
useSignIn(): UseMutationResult<UserRead, ApiFailure, { username: string; password: string }>
useSignOut(): UseMutationResult<void, ApiFailure, void>
```

`ApiFailure` is `{ code: string; status: number }`, produced by
`core/api/errors.ts` from the error envelope of §5.1 — or from a thrown fetch,
in which case `code` is `"NETWORK"` and `status` is `0`.

- `useCurrentUser` wraps the `["currentUser"]` query. Its query function
  returns `{ user, sessionExpired: false }` on `200`, and on a `401` returns
  `{ user: null, sessionExpired: code === "SESSION_EXPIRED" }` — a 401 is an
  expected state, not an error. Any other failure throws and surfaces as
  `isError`. The hook flattens the cached state into its return value.
  **There is no `wasAuthenticated` ref and no client-side memory of having
  been signed in**: the distinction between "never signed in" and "session
  expired" is the server's `code`, read straight off the response (§6.3 R14).
- `useSignUp` / `useSignIn` on success call
  `queryClient.setQueryData(["currentUser"], { user, sessionExpired: false })`
  and then navigate per `ui-spec.md` §6.5.
- `useSignOut` owns the deliberate sign-out redirect. In its success handler,
  **in this order**: `navigate("/signin", { replace: true })`, then
  `clearCsrfToken()`, then
  `queryClient.setQueryData(["currentUser"], { user: null, sessionExpired: false })`.
  `sessionExpired: false` is the belt to the ordering's braces: even if the
  guard did render, it could not claim an expiry. The order is the fix for
  the "signed out on purpose" case — see §6.3 R10 — and both updates are
  dispatched from one handler, so React commits them in a single render in
  which the location is already `/signin` and the cached user is already
  `null`. `RequireAuth` is unmounted in that render and never redirects.
- `useSignOut` treats a **401** (`NOT_AUTHENTICATED` or `SESSION_EXPIRED`)
  exactly like success and runs the same handler: the session is already gone,
  which is what the user asked for. `auth:signOut.error` is shown only for a
  `403`, a `5xx`, an unmapped code or a `NETWORK` failure (§6.3 R10).

The hook is named `useCurrentUser` and the query key is `["currentUser"]`, not
`useSession` / `["session"]`: `session` is taken twice over in this codebase —
by the HTTP session of §5.7 and by the SQLAlchemy `AsyncSession` — and
`project-vision.md` introduced `Playthrough` precisely to keep the word free.

**Routing** — declarative only. `react-router` v8; there is no
`react-router-dom` package any more. No data routers, no loaders, no actions:
authentication state comes from TanStack Query.

| Path | Element | Guard |
|---|---|---|
| `/` | `HomeRoute` (which itself renders `AppShell`) | `RequireAuth` |
| `/signin` | `SignInRoute` | `RequireAnonymous` |
| `/signup` | `SignUpRoute` | `RequireAnonymous` |
| `*` | `<Navigate to="/" replace />` | — |

Guard behaviour, every state, and where focus lands are pinned in
`ui-spec.md` §6.3–§6.5. `RequireAuth` remembers the attempted location in
router state as `from`, and adds `reason: "sessionExpired"` **exactly when
`sessionExpired` is true** — i.e. when the server answered `/users/me` with
code `SESSION_EXPIRED` rather than `NOT_AUTHENTICATED` (§6.3 R14).

**Dependencies.** `react@19.2`, `react-dom@19.2`, `@mui/material@9.4`,
`@emotion/react@11.14`, `@emotion/styled@11.14`,
`@tanstack/react-query@5.102`, `react-router@8.3`, `i18next@26.4`,
`react-i18next@17.0`, `openapi-fetch@0.17`.
Dev: `vite@8.2`, `@vitejs/plugin-react@6.1`, `typescript@5.9`,
`@types/react@19.2`, `@types/react-dom@19.2`, `@types/node@24`,
`eslint@10.10`, `typescript-eslint@8.70`, `eslint-plugin-react-hooks@7.1`,
`eslint-plugin-react-refresh@0.5`, `globals@17`, `vitest@5.0`, `jsdom@30`,
`@testing-library/react@16.3`, `@testing-library/dom@10.4`,
`@testing-library/jest-dom@7.0`, `@testing-library/user-event@14.6`,
`openapi-typescript@7.13`.

**TypeScript is pinned at 5.9, not 7.x, and this is deliberate**: it is the
only line that satisfies every peer range in the tree —
`typescript-eslint@8` requires `>=4.8.4 <6.1.0` and `openapi-typescript@7`
requires `^5.x`. Do not upgrade it in this step.
`@testing-library/dom` must be an explicit dev dependency: RTL 16 declares it
as a peer and does not bundle it.

`pnpm-workspace.yaml` contains only `onlyBuiltDependencies: []`. If
`pnpm install` reports ignored build scripts, add exactly the reported package
names to that list and say so in the report; change nothing else in that file.

**Scripts** in `package.json` — these exact names, because the `Makefile`,
`CLAUDE.md` and the Dockerfile call them:

```json
"dev": "vite",
"build": "tsc -b && vite build",
"lint": "eslint .",
"typecheck": "tsc -b --force",
"test": "vitest run",
"test:watch": "vitest",
"generate:api": "openapi-typescript openapi.json -o src/api/schema.d.ts"
```

`vite.config.ts` is a **plain object** `defineConfig({...})`, not a function,
so `vitest.config.ts` can `mergeConfig` it. It sets
`server: { host: "0.0.0.0", port: 5173, strictPort: true, watch: { usePolling: process.env.VITE_SERVER_USE_POLLING === "true" } }`.

`vitest.config.ts` merges `vite.config.ts` and adds
`test: { environment: "jsdom", globals: false, setupFiles: ["./src/test/setup.ts"], include: ["src/**/*.test.{ts,tsx}"], css: false }`.

### 6.3 Screens, copy and i18n — reconciliation with `ui-spec.md`

[`ui-spec.md`](ui-spec.md) is the authority for screen composition, MUI
component choice, every visual state, validation timing and messaging, focus
management, the a11y baseline and the **complete copy and i18n key table**
(its §7). None of that is restated here. Build both documents; where they
conflicted, the following rulings apply and nothing else is negotiable.

| # | Conflict | Ruling |
|---|---|---|
| R1 | URL paths — `/sign-in` `/sign-up` (earlier draft of this file) vs `/signin` `/signup` (ui-spec) | **`/signin` and `/signup`.** ui-spec wins; no backend consequence |
| R2 | Where `AppShell` lives — `src/components/AppShell.tsx` (ui-spec §1, earlier drafts of this file) vs its caller's module | **`frontend/src/modules/home/components/AppShell.tsx`. `src/components/` is empty in phase 0.** The component itself is adopted exactly as `ui-spec.md` §3 specifies — §3 and criteria UI-21, UI-22, UI-23, UI-25 and UI-35 stand at face value, AppBar clauses included, and the `title` + `action?: ReactNode` + `children` shape is unchanged. Only the path moves: `HomeRoute` is its sole caller, so D1's one-caller rule applies. It graduates to `src/components/` unchanged the moment a second module renders it. Owner ruling, §10 OQ-A |
| R3 | i18n — one namespace `translation` (earlier draft) vs `common` / `auth` / `home` with compile-checked keys (ui-spec §7) | **ui-spec wins in full**: `core/i18n/locales/en/{common,auth,home}.json`, `defaultNS = "common"`, `i18n.d.ts` declaring `CustomTypeOptions`, `useTranslation("auth")` per component |
| R4 | Current-user surface — `useSession` / `readSession` / `modules/auth/api.ts` (ui-spec §1) | **`useCurrentUser`, query key `["currentUser"]`, no `api.ts`** (§6.2). The endpoint is `GET /api/v1/users/me` |
| R5 | HTTP layer — "fetch wrapper" (ui-spec §1) vs the generated typed client | **`openapi-fetch` over the generated `paths` type** (§7 and D11). `core/api/errors.ts` provides the normalisation ui-spec §5 asks for |
| R6 | Anonymous-only guard — earlier draft said a signed-in visitor is not redirected | **ui-spec wins**: `RequireAnonymous` redirects to `/` |
| R7 | Submit-button busy state | **ui-spec wins**: MUI v9 `Button loading` with the `submitting` label. The earlier `startIcon` spinner is dropped |
| R8 | `theme.ts` | **ui-spec wins**: `cssVariables: true` and `colorSchemes: { light: true, dark: true }`, no palette overrides (§6.2) |
| R9 | MUI major — ui-spec OQ-7 was written against **v7**, which is stale | **`"@mui/material": "^9.4.0"`.** Owner-verified: `latest` is `9.4.0` and `7.3.11` sits as `latest-v7`. All three APIs ui-spec relies on exist in v9 unchanged (`Button` `loading`, `slotProps.htmlInput`, `colorSchemes` + `cssVariables`), so **use ui-spec's v9 phrasing, never its v7 fallbacks** — no `LoadingButton` from `@mui/lab`, no `inputProps`, no `useMediaQuery("(prefers-color-scheme: dark)")` theme. Additionally: v9 layout components take no system props (use `sx`) and `Grid` takes `size`. See `shared-knowledge.md` D14 |
| R10 | Session expiry and the sign-out redirect — ui-spec §6.3 gave `core/api` two different cache jobs: a 401 on a mutation makes "`core/api` set the session query data to `null`", and the guard redirects on "the next mutation (401 → `core/api` invalidates the session query)" | **Both sentences are unimplementable as written, and both are replaced — including the "invalidates" one, which describes exactly the global 401 interceptor D21 bans.** `createQueryClient()` is a factory and `core/api` holds no reference to the instance, so `core/api/client.ts` keeps its single CSRF job and never touches the cache: it neither writes nor invalidates `["currentUser"]`. Two owners, one trigger each, and they cannot both fire: **(a)** deliberate sign-out is owned by `modules/auth/hooks/useSignOut.ts`, which navigates to `/signin` first and then clears (§6.2), passes **no** router state, and therefore shows **no** "session ended" warning; **(b)** expiry-during-session is discovered only by the `["currentUser"]` query itself and is owned by `modules/auth/components/RequireAuth.tsx`, which redirects to `/signin` with `{ from, reason: "sessionExpired" }` when the query resolves to no user **and the server said `SESSION_EXPIRED`** (R14). A **401 on the sign-out request is case (a)**, never (b): the session is already gone, so it runs the success handler and no `auth:signOut.error` alert appears. `auth:signOut.error` covers `403`, `5xx`, an unmapped code and `NETWORK` only |
| R11 | ui-spec §5's "Server-side validation failed (422) → field error(s) via `details`" | **Dropped. A 422 maps to `common:errors.unexpected`, full stop.** The client mirrors the server's rules (§6.4 OQ-2/OQ-3), so a 422 from either auth form is unreachable without a client bug; a mapping layer no test can reach is worse than no layer. `details.fields` stays in the wire contract (§5.1) for operators and for later steps, and nothing in the frontend reads it |
| R12 | Who mounts the providers — ui-spec is silent, and earlier drafts of this file put `ThemeProvider` in `App.tsx` | **The full stack lives in `main.tsx`; `App.tsx` is `<Routes>` only.** Exact nesting in §6.2. A test renders `<App />` (or a single route component) inside `renderWithProviders`, which supplies the same providers with a `MemoryRouter` |
| R13 | Criterion numbering — `ui-spec.md` §12 numbers 1–38 while this file's §8 numbers 1–45 | **ui-spec §12 criteria are `UI-1 … UI-43` and are prefixed that way in §12 itself.** Unprefixed numbers always mean this file's §8. UI-39…UI-43 were appended after that ruling and are in force exactly like UI-1…UI-38 |
| R14 | The expired-versus-never-signed-in split — ui-spec §6.3 derives it from a client-side `wasAuthenticated` ref inside `useSession()` | **The ref is dropped. The signal is the server's error `code`.** `GET /api/v1/users/me` already answers `SESSION_EXPIRED` and `NOT_AUTHENTICATED` distinctly (§5.6), so `useCurrentUser` reads the reason off the response and exposes `sessionExpired: boolean`; `RequireAuth` adds `reason: "sessionExpired"` exactly when that is true. One mechanism instead of two, server truth instead of a ref that must be kept in sync, and the "first-time visitor told their session ended" defect becomes unrepresentable. `NOT_AUTHENTICATED` means *no cookie was sent*; a present-but-unresolvable cookie is `SESSION_EXPIRED` and **does** produce the warning — pinned in §5.6, accepted knowingly |

#### 6.3.1 Who mounts what — the composition table

`ui-spec.md` names screens and components; this table pins the mounting chain,
so no two files claim the same responsibility. It is authoritative.

| Rendered by | Renders | Notes |
|---|---|---|
| `main.tsx` | the provider stack, then `<App />` | the only file with providers; the only `BrowserRouter` |
| `App.tsx` | `<Routes>` with the four routes of §6.2 | no provider, no router, no layout |
| route element `/` | `<RequireAuth><HomeRoute /></RequireAuth>` | the guard owns the pending spinner and the error/retry state (`ui-spec.md` §6.3), so no shell flashes before the user is known |
| `HomeRoute` | `<AppShell title={t("common:app.title")} action={<SignOutButton … />}>` + the greeting and, when present, the sign-out error `Alert`, as `children` | calls `useSignOut()` **once**; the only owner of that mutation |
| `AppShell` | `AppBar` / `Toolbar` / title / the `action` slot / `Box component="main"` > `Container` > `children` | imports nothing from any module; no hook of its own |
| `SignOutButton` | one MUI `Button` | **presentational**: it takes `onClick` and `loading` as props and calls no hook. `HomeRoute` passes them from its single `useSignOut()` instance |
| route elements `/signin`, `/signup` | `<RequireAnonymous><SignInRoute /></RequireAnonymous>` etc. | each route renders `AuthCard` + its form (`ui-spec.md` §3.1, §3.2) |

`modules/home` importing `SignOutButton`, `useSignOut` and `useCurrentUser`
from `modules/auth` is the **one** cross-module dependency permitted in this
step, and it is named here because `architecture.md` requires cross-module use
to be stated in the step spec. Nothing else crosses a module boundary, and
`modules/auth` imports nothing from `modules/home`. `App.tsx` rendering
`RequireAuth` / `RequireAnonymous` is not a cross-module import: `App.tsx` is
not a module.

The sign-out mutation is instantiated in exactly **one** component
(`HomeRoute`): one mutation instance, one owner, no context, no store, no
second `action` slot. `ui-spec.md` §3.3's row "Action slot … filled with
`<SignOutButton />`" resolves to the two rows above.

### 6.4 Answers to `ui-spec.md` §11 open questions

| ui-spec | Answer |
|---|---|
| OQ-1 — does sign-up create the session? | **Yes.** `POST /api/v1/auth/register` returns 201 with the session cookie and the CSRF header (§5.3), so sign-up lands on `/`. The `accountCreated` alternative and its key are not needed |
| OQ-2 — username rules | `USERNAME_MIN = 3`, `USERNAME_MAX = 32`, `USERNAME_PATTERN = /^[A-Za-z0-9_-]+$/`. The assumed wording "letters, numbers, underscore, hyphen" is correct. Note the server lower-cases the stored value, so the greeting shows the lower-cased username |
| OQ-3 — password rules | `PASSWORD_MIN = 8`, `PASSWORD_MAX = 128` — a maximum does exist, so `validation.password.tooLong` is needed. No complexity rules |
| OQ-4 — error codes and 422 `details` | The complete code table is §5.1. On the wire, `details` for a 422 is `{"fields": [ … ]}`, each entry a Pydantic error object with `loc`, `msg` and `type`. **The frontend does not read it**: a 422 maps to `common:errors.unexpected` like any unmapped failure (§6.3 R11). The client mirrors the server's rules, so a 422 from either form means a client bug, not a user mistake |
| OQ-5 — endpoints, session-read shape, CSRF | Endpoints: §5.2–§5.6. The current-user read is `GET /api/v1/users/me` → `{ id, username, createdAt }`. The CSRF token arrives in the `X-CSRF-Token` **response header** of register, sign-in and `/users/me`, and is stored and replayed by the client middleware (§6.2). **No extra request, no pre-flight fetch, no second spinner.** A CSRF rejection is `403 CSRF_TOKEN_INVALID`; treating it as `common:errors.unexpected` is correct |
| OQ-6 — is sign-in rate-limited? | **No.** Nothing in step 0.1 rate-limits. Do not design a lockout message |
| OQ-7 — the MUI major | **v9.4** — see R9 |

Three further constraints ui-spec asks for and this file answers:

- **Which code drives the redirect reason** (its §6.3): the reason comes from
  the `code` in the `401` error envelope of `GET /api/v1/users/me`.
  `SESSION_EXPIRED` → redirect to `/signin` with
  `{ from, reason: "sessionExpired" }` → the warning Alert of ui-spec §6.1.
  `NOT_AUTHENTICATED` → redirect with `{ from }` only and **no** message. No
  other code reaches this path, and nothing on the client remembers whether a
  user was previously loaded (§6.3 R14).

- Timing parity on sign-in (its §5.1): the unknown-username path performs an
  Argon2 verification against a fixed dummy hash, so the two failures take
  comparable time (§5.4, §6.1).
- No icon package: `@mui/icons-material` is absent from the dependency list of
  §6.2 by design.

### 6.5 Backend test arrangement — the engine/event-loop trap

The suite stays fully synchronous and never constructs an engine. Binding
arrangement:

1. `backend/tests/conftest.py` pins the environment before importing the app —
   `DATABASE_URL`, `ENVIRONMENT=development`, `SESSION_TTL_SECONDS`,
   `FRONTEND_ORIGIN` — then calls `get_settings.cache_clear()`. The root
   `.env` is not inside `backend/`, so it cannot leak in, but pin the values
   anyway.
2. Tests build the app with `create_app()` and drive it with
   `fastapi.testclient.TestClient`. No `pytest-asyncio`, no async fixtures.
3. `app.dependency_overrides[get_db_session]` returns a trivial stub object.
   The stub is never actually used, because
4. route-level tests monkeypatch the **pinned service functions** of §6.1
   (`monkeypatch.setattr(app.modules.users.service, "create_user", …)`) with
   `unittest.mock.AsyncMock` or plain async stubs. That is why those
   signatures are contract: they are the test seam. It works **only** because
   routes and dependencies hold a module reference and call
   `service.create_user(...)` — the call style pinned in §6.1, which nothing
   may deviate from.
   Any authenticated route needs **two** stubs, not one:
   `auth.service.resolve_session` and `users.service.get_user_by_id`, in that
   order (§6.1).
5. `get_engine()` / `get_sessionmaker()` are therefore never called, and
   `cache_clear()` on them is never needed. If a future step needs a real
   database in tests, it builds its own engine in the fixture rather than
   going through the cached accessors.

Pure units — `normalize_username`, `hash_password`/`verify_password`,
`generate_token`/`hash_token`/`tokens_equal` — are tested directly.

To exercise the 500 envelope, use
`TestClient(app, raise_server_exceptions=False)`; Starlette re-raises server
exceptions to the test client otherwise.

For criterion 28's log assertion the mechanism is **`capsys`, not `caplog`**:
structlog writes to `sys.stderr` and never touches stdlib `logging`, so
`caplog` records nothing. `capsys` only captures what is written after pytest
replaced `sys.stderr`, so the test calls `configure_logging()` itself, inside
the test, before triggering the failing route (§6.1 requires that to be safe
to do).

`backend/tests/` mirrors the modules one-to-one: `tests/conftest.py`,
`tests/core/`, `tests/health/`, `tests/users/`, `tests/auth/`.

### 6.6 Frontend test arrangement — owned by qa-frontend

**`frontend/src/test/**` belongs to qa-frontend in whole**, together with
`vitest.config.ts`'s `setupFiles` target. It is test infrastructure whose only
consumer is qa-frontend, so qa-frontend shapes those helpers as its suites
need — signatures included. frontend-dev creates no file under `src/test/`
and imports none.

Three constraints, and nothing else is pinned here:

1. **One fetch dispatcher, installed once at startup.**
   `openapi-fetch`'s `createClient` captures `globalThis.fetch` when
   `core/api/client.ts` is evaluated, so the dispatcher must be installed in
   the setup file — before any test module imports the client — and must never
   be replaced afterwards. Stubbing is done by re-registering routes on that
   one dispatcher.
2. **An unstubbed request throws.** A missing stub must be a loud failure, not
   a silent network error that a component renders as `common:errors.network`.
3. **Requests are relative.** `VITE_API_URL` is undefined under vitest, so
   `client.ts` gets `baseUrl: undefined` and the paths the dispatcher sees are
   `/api/v1/...`. qa-frontend decides what to do about that (match on the
   path, or define the variable in the vitest env) — it is a test-side
   decision.

The providers a test needs, and what a test renders, are pinned in §6.2 under
"Provider composition" and in §6.3.1: `<App />` carries no router and no
provider, so a render helper supplies `ThemeProvider` + `CssBaseline`,
`I18nextProvider`, `QueryClientProvider` with a **fresh** `createQueryClient()`
per test, and a `MemoryRouter`.

## 7. The typed-client bootstrap

`make generate-api` needs a running `app-web`, so `src/api/schema.d.ts` cannot
be generated from the real backend before the backend exists. The resolution,
in order:

1. **`frontend/openapi.json` is committed with this spec.** It is the wire
   contract of §5 expressed as the OpenAPI 3.1 document FastAPI will produce.
   Neither dev agent hand-edits it.
2. **frontend-dev runs `pnpm generate:api`** against that file to produce
   `src/api/schema.d.ts` and commits the result. The file is therefore
   genuinely machine-generated — there is no hand-written type masquerading as
   a generated one — and frontend-dev is fully type-safe from minute one.
3. **`frontend/openapi.json` is normative for backend-dev as well**, not only
   for frontend-dev. §5 and the pinned names of §6.1 fix the routes,
   `operationId`s (from the route function names), component names (from the
   schema class names), the `responses=` status sets, and the absence of
   docstrings and field `description=`s — but field types, constraints,
   `required`-ness, tags and the decorator paths change the export too, and
   only `openapi.json` pins those. **Read it and match it.** Three traps it
   already answers, all verifiable in the committed file:

   - `ErrorBody.details` is in `required`. Declare it `details: dict[str, Any]
     | None` **with no default** — `= None` makes it optional and drops it
     from `required`.
   - `HealthRead.status` is a plain `"type": "string"`. Declare it
     `status: str`; `Literal["ok"]` emits `"const": "ok"` and diverges.
   - The health route decorator path is `@router.get("")`, **not** `"/"`.
     With the router mounted at prefix `/health`, `"/"` yields the path
     `/api/v1/health/` and moves the whole entry in the document.
4. **At the close of the step the owner runs `make up && make generate-api`**
   and inspects `git diff frontend/`. Note that this command **overwrites**
   `frontend/openapi.json` from the running app before `schema.d.ts` is
   regenerated from it, so the prediction is destroyed by the check that uses
   it: qa-backend must capture `git diff frontend/openapi.json` **and**
   `git diff frontend/src/api/schema.d.ts`, both verbatim, in the same report
   (criterion 31). `src/api/schema.d.ts` is expected to be unchanged;
   `openapi.json` may differ in key order and `title` values — harmless,
   `openapi-typescript` ignores both. Any change to a path,
   `operationId`, schema name, property name, optionality or status-code set is
   a **contract violation**, and the backend is what gets corrected, not the
   spec.

That last check is acceptance criterion 31 and belongs to qa-backend.

## 8. Acceptance criteria

Numbered, each provable or refutable without reading the implementation.
Owner column: **B** = qa-backend, **F** = qa-frontend.

### Environment and boot

| # | Criterion | Owner |
|---|---|---|
| 1 | `make build` completes for every service in `compose.yaml`, including the `cli` profile. | B |
| 2 | `make up` brings `postgres`, `app-web` and `frontend` to running; `app-web` logs "Running database migrations ..." then a uvicorn startup line, and does not restart. | B |
| 3 | `GET http://localhost:8000/api/v1/health` returns `200` and exactly `{"status":"ok"}`. | B |
| 4 | `http://localhost:8000/docs` renders in the default (`development`) configuration. | B |
| 5 | `http://localhost:5173/` serves the SPA; the Vite dev server is reachable from the host. | F |
| 6 | `make backend-lint`, `make frontend-lint` and `make frontend-typecheck` all exit 0. | B / F |
| 7 | `make backend-test` and `make frontend-test` both run with the stack **down**. | B / F |

### Migrations

| # | Criterion | Owner |
|---|---|---|
| 8 | `alembic current` reports head `0001` after boot. | B |
| 9 | `alembic downgrade base` succeeds and leaves neither `users` nor `sessions` in the database; a following `alembic upgrade head` recreates both. | B |
| 10 | `users.username` has a unique constraint; `sessions.token_hash` has a unique constraint; `sessions.user_id` is a FK to `users.id` with `ON DELETE CASCADE`. | B |
| 11 | There is no `role` column on `users` and no vector column anywhere. | B |

### Registration

| # | Criterion | Owner |
|---|---|---|
| 12 | `POST /api/v1/auth/register` with `{"username":"Aragorn","password":"hunter-of-orcs"}` returns `201`, a body whose `username` is `"aragorn"`, an `id` that parses as a UUID, a `createdAt` that parses as a date, a `Set-Cookie` for `session`, and an `X-CSRF-Token` response header. | B |
| 13 | The `session` cookie carries `HttpOnly`, `Path=/`, `SameSite=Lax`, a `Max-Age` equal to `SESSION_TTL_SECONDS`, and **no** `Secure` flag in the development configuration. | B |
| 14 | Registering `aragorn` again returns `409` with code `USERNAME_TAKEN`; registering `ARAGORN` also returns `409`. | B |
| 15 | `{"username":"ab","password":"hunter-of-orcs"}`, `{"username":"ara gorn",…}` and `{"username":"aragorn","password":"short"}` each return `422` with code `VALIDATION_ERROR` and a `details.fields` array. | B |
| 16 | The stored `password_hash` is an Argon2 encoded hash (starts with `$argon2`) and is not the submitted password. | B |
| 17 | The value of the `session` cookie does not appear in the `sessions` table; `sessions.token_hash` is 64 lower-case hex characters. | B |

### Sign-in, current user, sign-out

| # | Criterion | Owner |
|---|---|---|
| 18 | `POST /api/v1/auth/sign-in` with correct credentials returns `200`, the `UserRead` body, a new `session` cookie and an `X-CSRF-Token` header; the cookie value differs from the one issued at registration. | B |
| 19 | Sign-in with an unknown username and sign-in with a wrong password both return `401` with code `INVALID_CREDENTIALS` and the identical body. | B |
| 20 | Sign-in with `{"username":"ara gorn","password":"x"}` returns `401 INVALID_CREDENTIALS`, **not** `422` — the sign-in schema has no pattern. | B |
| 21 | `GET /api/v1/users/me` with a valid cookie returns `200`, the `UserRead` body and an `X-CSRF-Token` header equal to the one issued at sign-in. | B |
| 22 | `GET /api/v1/users/me` with no cookie returns `401 NOT_AUTHENTICATED`; with a syntactically valid but unknown cookie it returns `401 SESSION_EXPIRED` and a `Set-Cookie` clearing `session`. | B |
| 23 | `POST /api/v1/auth/sign-out` with a valid cookie and the matching `X-CSRF-Token` returns `204`, clears the `session` cookie, and a subsequent `GET /users/me` with the old cookie returns `401 SESSION_EXPIRED`. | B |
| 24 | `POST /api/v1/auth/sign-out` with a valid cookie and no `X-CSRF-Token` returns `403 CSRF_TOKEN_INVALID`; with a wrong token, likewise. The session remains usable afterwards. | B |
| 25 | `POST /api/v1/auth/sign-out` with no cookie returns `401 NOT_AUTHENTICATED` — authentication is checked before CSRF. | B |

### Envelope, CORS, observability

| # | Criterion | Owner |
|---|---|---|
| 26 | Every non-2xx response in criteria 14–25 has the body shape `{"error":{"code":…,"message":…,"details":…}}` and no other top-level key. | B |
| 27 | `GET /api/v1/does-not-exist` returns `404 NOT_FOUND` in the envelope; `GET /api/v1/auth/sign-in` returns `405 METHOD_NOT_ALLOWED` in the envelope. | B |
| 28 | An endpoint made to raise returns `500` with code `INTERNAL_ERROR` and a body containing neither the exception type nor a traceback, while the traceback is present in the log. | B |
| 29 | A preflight `OPTIONS` to `/api/v1/auth/sign-in` from `Origin: http://localhost:5173` with `Access-Control-Request-Method: POST` and `Access-Control-Request-Headers: content-type, x-csrf-token` returns `access-control-allow-credentials: true`, `access-control-allow-origin` equal to that exact origin (never `*`), and `x-csrf-token` in `access-control-allow-headers`, compared case-insensitively. **Do not assert `access-control-expose-headers` on the preflight:** Starlette's `CORSMiddleware` puts it in the simple-response header set only, so a byte-correct configuration omits it here. | B |
| 30 | The `200` response to `POST /api/v1/auth/sign-in` sent with `Origin: http://localhost:5173` carries `access-control-expose-headers` containing `x-csrf-token`, alongside `access-control-allow-credentials: true` and that exact origin. | B |
| 31 | After `make generate-api` against the running stack, `git diff --exit-code frontend/src/api/schema.d.ts` reports no change. **On a diff, do not report a backend defect yet:** `frontend/openapi.json` was a hand-authored prediction of FastAPI's output, so it is an equally likely cause — and `make generate-api` has just overwritten it. Report **both** `git diff frontend/openapi.json` and `git diff frontend/src/api/schema.d.ts` verbatim, with both candidate causes named, and let the **owner** arbitrate which document is wrong; only the owner authorises a change to either the backend or the committed `openapi.json`. | B |
| 32 | Application log lines go to **stderr**; `docker compose exec -T app-web app openapi export` writes parseable JSON and nothing else to stdout. | B |

### Frontend behaviour

`ui-spec.md` §12 carries its own numbered criteria, prefixed **`UI-1` …
`UI-43`** in that document (§6.3 R13), covering screen composition,
validation, states, focus and a11y; qa-frontend rules on those too. They stand
**as written, AppBar clauses included** — UI-21, UI-22, UI-23, UI-25 and UI-35
are in force verbatim, against `AppShell` at its `modules/home/components/`
path (§6.3 R2). The only adjustment is UI-20, which takes the "lands on `/`"
branch because §6.4 answers ui-spec OQ-1 yes. An unprefixed number anywhere in
either document means a criterion of this §8. The criteria below prove the
*wire* contract and the *composition* contract from the browser and are not in
the `UI-` list.

| # | Criterion | Owner |
|---|---|---|
| 33 | Visiting `/` while signed out ends on `/signin` without a full page reload. | F |
| 34 | The sign-up form registers a new user and lands on `/`, whose greeting shows the **lower-cased** username the server returned, even when the form was filled with mixed case. | F |
| 35 | Signing up with a taken username keeps the user on `/signup`, marks the username field `aria-invalid="true"` and shows the `auth:signUp.error.usernameTaken` copy — never the server's English `message`. | F |
| 36 | Signing in with wrong credentials shows the `auth:signIn.error.invalidCredentials` copy and stays on `/signin`. | F |
| 37 | Reloading `/` while signed in keeps the user signed in, and a subsequent sign-out still succeeds — proving the CSRF token was re-acquired from the `X-CSRF-Token` header of `GET /api/v1/users/me`. | F |
| 38 | A sign-out request carries an `X-CSRF-Token` request header; a `GET` request carries none. | F |
| 39 | The browser sends credentials: the network log shows the `session` cookie on `GET /api/v1/users/me`, and the request is cross-origin (`http://localhost:5173` → `http://localhost:8000`). | F |
| 40 | Nothing reads or writes `document.cookie`, `localStorage` or `sessionStorage`; grepping `frontend/src` finds no occurrence. | F |
| 41 | Every rendered word traces to a key in `src/core/i18n/locales/en/{common,auth,home}.json`; no component contains a user-facing string literal. | F |
| 42 | Module-boundary greps, all three of which must hold: (a) `src/components/` contains no `.ts` or `.tsx` file; (b) `AppShell.tsx` is at `src/modules/home/components/` and **no import path in it contains `modules/`** — the frame knows nothing of any module; (c) grepping `src/modules/home/**` for `auth/` finds only `SignOutButton`, `useSignOut` and `useCurrentUser`; grepping `src/modules/auth/**` for `home/` finds nothing; and there is no `modules/auth/api.ts`. | F |
| 43 | `src/core/` holds exactly the files listed in §6.2 — no `config.ts` and no additions — **no `.tsx` file at all** (`core/` holds infrastructure, never UI), and **no file under `src/core/` imports anything from `src/modules/`** (grep for `modules/` under `src/core/` finds nothing). That, plus 42(c), is the module-boundary property; the "two module callers" bar of D1 governs new *helpers and components*, not the per-app singletons `core/` exists for, so it is not asserted of `client.ts`, `errors.ts`, `theme.ts`, `queryClient.ts` or `i18n/`. | F |
| 44 | `src/api/schema.d.ts` is byte-identical to the output of `pnpm generate:api` — the committed types are generated, not hand-written. | F |
| 45 | Signing out from `/` lands on `/signin` and shows **no** warning Alert — the `auth:signIn.sessionExpired` copy is absent from the document. A cold load of `/` whose `["currentUser"]` read answers `401 SESSION_EXPIRED` **does** show it; a cold load of `/` answering `401 NOT_AUTHENTICATED` does **not**; a direct visit to `/signin` shows no warning whatever the code, because the warning is driven by `RequireAuth`'s router state. In step 0.1 the only trigger for that read is a mount — there is no polling, no window-focus refetch and no mutation-driven invalidation. | F |
| 46 | `src/App.tsx` contains no provider and no router: grepping it finds no `Provider`, no `BrowserRouter` and no `MemoryRouter`. `src/main.tsx` is the only file containing `BrowserRouter`, and rendering `<App />` inside qa-frontend's own provider wrapper does not throw. | F |

## 9. The parallelisation split

Neither dev agent may create, edit or delete a file outside its list. Neither
may touch `compose.yaml`, `compose.langfuse.yaml`, `Makefile`, `.env.dist`,
`.env`, `docker/*`, `.gitignore`, `.dockerignore`, `README.md`, `.claude/**` or
`docs/general/**`.

### backend-dev owns — everything under `backend/`

```
backend/.python-version
backend/pyproject.toml
backend/uv.lock                       (produced by `uv lock`)
backend/alembic.ini
backend/alembic/env.py
backend/alembic/script.py.mako
backend/alembic/versions/0001_baseline.py
backend/app/**                        (§6.1 tree)
```

Not backend-dev's: `backend/tests/**` (qa-backend), anything under
`frontend/`.

Static checks backend-dev runs: `ruff check .`, `ruff format --check .`, the
Alembic up/down/up round-trip against the Compose Postgres, and that
`create_app()` imports and the container boots. **Not** `pytest`.

### frontend-dev owns — everything under `frontend/` except the two files below

```
frontend/package.json
frontend/pnpm-lock.yaml               (produced by `pnpm install`)
frontend/pnpm-workspace.yaml
frontend/tsconfig*.json
frontend/vite.config.ts
frontend/vitest.config.ts
frontend/eslint.config.js
frontend/index.html
frontend/public/**                    (a favicon only, if index.html references one)
frontend/.gitignore                   (frontend-local ignores only)
frontend/src/api/schema.d.ts          (generated via `pnpm generate:api`, committed)
frontend/src/main.tsx
frontend/src/App.tsx
frontend/src/core/**
frontend/src/modules/**
```

`frontend/src/components/` is created empty (or not created at all —
frontend-dev's choice; nothing may be put in it, criterion 42a).

Not frontend-dev's: `frontend/openapi.json` (this spec's artefact — read-only
input, and normative for both dev agents), `frontend/src/test/**` (qa-frontend),
`frontend/src/**/*.test.{ts,tsx}` (qa-frontend), anything under `backend/`.
frontend-dev writes `vitest.config.ts` with
`setupFiles: ["./src/test/setup.ts"]` pointing into qa-frontend's tree and
creates no file there.

Static checks frontend-dev runs: `pnpm lint`, `pnpm typecheck`, `pnpm build`.
**Not** `vitest`, **not** Playwright.

### qa-backend owns

```
backend/tests/**
```

### qa-frontend owns

```
frontend/src/test/**                  (setup.ts, render helper, fetch dispatcher)
frontend/src/**/*.test.{ts,tsx}
frontend/tests/**                     (Playwright specs, if any)
frontend/playwright.config.ts         (if needed)
```

The shared helpers are qa-frontend's outright (§6.6): their only consumer is
the test suite, and their signatures are qa-frontend's to choose. The three
constraints that survive the boundary — one fetch dispatcher installed at
startup, an unstubbed request throws, `VITE_API_URL` is undefined under
vitest — are in §6.6, and the providers a test must supply are in §6.2.

### Shared read-only inputs

`docs/roadmap/phase-0/step-0.1.md`, `docs/roadmap/phase-0/ui-spec.md`,
`docs/roadmap/phase-0/shared-knowledge.md`, `docs/general/architecture.md`,
`docs/general/backend-stack.md`, `docs/general/frontend-stack.md`,
`frontend/openapi.json`.

Both dev agents append cross-step decisions to
`docs/roadmap/phase-0/shared-knowledge.md` under `## Landed decisions`. That
file is the only shared writable target; append only, never rewrite another
agent's entry.

## 10. Owner rulings — all open questions closed

Nothing in this section is still open. It is kept because the reasoning is
precedent.

### OQ-A — the home page shell: **adopt `AppShell`, in `modules/home/`**

Two owner rulings, in order.

**The component is adopted.** The ux-designer had been commissioned to "design
the app shell that holds it (whatever nav is genuinely needed to sign out),
since that shell is what later phases extend"; this file's brief described
`src/components/` only as "genuinely shared UI only" and never as
required-empty. The shell was in scope, and `ui-spec.md` §3 stands at face
value, AppBar clauses and criteria UI-21/22/23/25/35 included. "Nothing else on
it" still governs the home page's **content** (§1).

**Its placement is reversed.** The first ruling put it in
`frontend/src/components/`, on the strength of "two module callers on day one".
`spec-reviewer` showed that claim is false: `/` is the only route that renders
`AppShell`, so `HomeRoute` is its sole caller, and it is `HomeRoute` — not
`modules/auth` — that imports `SignOutButton` to fill the `action` slot.
`modules/auth` never renders `AppShell`. One caller means D1's own rule
applies, and the file lives at
`frontend/src/modules/home/components/AppShell.tsx`. `src/components/` is empty
in phase 0.

That makes the precedent **stronger**, not weaker: the rule bit on the very
first case and overrode an owner ruling in the process, which is exactly what a
rule is for. The rule now reads: two or more **module** callers, counted as
modules that actually render the file, with the file itself importing nothing
from any of them. `AuthCard` is the first worked example (two callers, both
inside `modules/auth`, so it stays there); `AppShell` is the second (one module
caller, so it lives in that module and graduates to `src/components/` unchanged
when a second module renders it — the expected path for shared UI here: born in
its module, promoted on evidence). Both examples exist to be argued against
later. Recorded in `shared-knowledge.md` D1.

### OQ-B — `.env.dist` and `README.md`: **applied**

All four items landed in the owner's words; see §3. Declared settings are
exactly five. Dev agents must not touch either file.

### OQ-C — the vision document: **closed**

`authentication` is struck from the "Out of scope" line of
`docs/general/project-vision.md`, which now reads "multiplayer, maps, voice".
It no longer lists `external APIs`, so the contradiction with the
portrait-generating character agent of its §1 and with `135.md`'s external-API
bonus target is **gone**; nothing is outstanding there. Leave that line alone —
not a phase-0 concern either way.

### OQ-D — expired session rows: **deferred, and recorded**

No sweeper in this step; there is no job runner. Logged as known future work in
`shared-knowledge.md` so it is not rediscovered as a bug: an
`app sessions prune` Typer command.

### OQ-E — colour schemes: **keep**

`cssVariables: true` and `colorSchemes: { light: true, dark: true }`, no
palette overrides. Two lines for theme correctness is a fair trade.

### MUI major: **v9 confirmed independently**

`latest` is `9.4.0`; `7.3.11` sits as `latest-v7`. `ui-spec.md` OQ-7's v7
assumption is stale and its v7 fallbacks must not be used. Pin and the three
divergent APIs are in §6.3 R9 and `shared-knowledge.md` D14.
