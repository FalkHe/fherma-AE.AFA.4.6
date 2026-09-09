# Backend stack

Python. The conventions that go with the stack; layer boundaries and the
modular placement rules are in [architecture.md](architecture.md), per-module
detail in each `backend/app/modules/<module>/README.md`. Where this document
and the code disagree, the code wins.

## Libraries

FastAPI (app factory `app.main:create_app`) on uvicorn, Pydantic v2 and
pydantic-settings, SQLAlchemy 2 async over psycopg 3, Alembic, Typer (console
script `app`), argon2-cffi, structlog. LangChain / LangGraph are declared but
not wired yet. Versions and floors live in `backend/pyproject.toml` and the
committed `backend/uv.lock`; Python is pinned to 3.12.

Two packaging consequences of `uv sync --locked`, which installs the project
plus default dependency *groups* and no extras: dev dependencies (pytest,
httpx, ruff) belong in **`[dependency-groups] dev`**, never in
`[project.optional-dependencies]`; and the build backend is `hatchling` with
`packages = ["app"]`, because `[project.scripts]` needs a wheel.

## Conventions

### Services

A service function takes the `AsyncSession` first and positionally, the rest
keyword-only:

```python
async def create_user(db: AsyncSession, *, username: str, password: str) -> User: ...
```

Mutating functions call `await db.commit()` themselves. Because the test suite
is authored against them before the implementation exists, exported service
function names and signatures are **contract**, pinned in the step spec;
changing one is a spec amendment.

### Sessions and the engine

`app/core/db.py` holds `Base`, `get_engine()`, `get_sessionmaker()`,
`get_db_session()` and the `DbSession` annotated alias. The two accessors are
`@lru_cache`d and are called **only** from `get_db_session` — never at import
time, never from a lifespan handler; the cache is process-wide rather than per
event loop, so an engine built outside the serving loop breaks async tests.
See `.claude/skills/qa-checklist/SKILL.md`.

### Schemas

Every request and response model derives from the shared camelCase base
`CamelModel` in `app/core/schemas.py`.

Schema class names become OpenAPI component names and route function names
become `operationId`s, both of which the committed
`frontend/src/api/schema.d.ts` depends on. Route functions therefore carry
**no docstrings** and fields no `description=`: explanatory prose goes in a `#`
comment above the decorator, so the exported schema stays stable. Each route
declares its failure `responses=` explicitly, so every status the client can
receive reaches the generated types.

### Errors

`app/core/errors.py` holds `ErrorCode`, the `ApiError` exception and
`register_error_handlers(app)`, which covers `ApiError`,
`RequestValidationError`, Starlette's `HTTPException` and a catch-all
`Exception`, so every failure leaves as the envelope in
[architecture.md](architecture.md) and nothing about an unhandled exception
reaches the client.

Raise `ApiError` from services, not `HTTPException` from routes. That handler
is also what clears the session cookie on `SESSION_EXPIRED`: a dependency that
raises has its injected `Response` discarded, so `require_auth` cannot do it
itself. Routes and dependencies never construct a `Response` — they take
`response: Response`, set cookies and headers on it, and return the model or
`None`, which FastAPI merges even into a bodiless `204`.

### Logging

`configure_logging()` in `app/core/logging.py` sets up structlog writing to
**stderr**. Stdout is reserved for command output, so
`app openapi export > frontend/openapi.json` produces valid JSON. Never log a
password, a session token or a CSRF token.

### Security primitives

`app/core/security.py` is the only place that touches cryptography: Argon2
password hashing with library defaults (no tuning, no rehash-on-verify),
token generation, SHA-256 token hashing and constant-time comparison. It is in
`core/` because both `users` and `auth` call it.

### Configuration

One `Settings` class in `app/core/settings.py`, reached through an `@lru_cache`d
`get_settings()`. Only what the code actually reads is declared, and
`extra="ignore"` means `.env.dist` may document variables a later phase will
use. Never read `os.environ` outside `settings.py`.

## Migrations

`alembic/env.py` takes the URL from `get_settings().database_url`, so
`sqlalchemy.url` in `alembic.ini` stays empty. `env.py` imports each module's
models explicitly for `target_metadata` — a new module adds one line; there is
no autodiscovery.

Every migration must round-trip: `upgrade head` → `downgrade base` →
`upgrade head` against a fresh database, with `downgrade()` dropping in reverse
dependency order. The web container runs `alembic upgrade head` on every boot,
so a failing migration takes the API down — verify the round-trip before
landing.

## CLI

`app/cli.py` exposes `cli = typer.Typer()`, registered as the `app` console
script, with commands grouped into sub-apps. A command that produces data
writes **only** that data to stdout; `app openapi export` is what
`make generate-api` redirects into `frontend/openapi.json`.

Use the CLI for anything that is not a request — seeding, ingestion, one-off
maintenance. There is no job runner to use instead.

## Tests and tooling

Commands are listed in `.claude/CLAUDE.md`; ruff and pytest are configured in
`pyproject.toml`. One setting to know: `filterwarnings = ["error"]` — any
warning fails the suite.

The suite is fully synchronous and never constructs a database engine:

- `tests/conftest.py` pins the environment variables before the app is imported
  and clears the settings cache, so the root `.env` cannot influence a run.
- Tests drive the app with `TestClient` and the CLI with Typer's `CliRunner`.
  There is no `pytest-asyncio` and there are no async fixtures.
- `app.dependency_overrides[get_db_session]` returns a stub and route tests
  monkeypatch the pinned service functions, so the engine accessors are never
  called. This works only because of the module-reference call style in
  [architecture.md](architecture.md).
- To observe the 500 envelope, use `TestClient(app,
  raise_server_exceptions=False)`.
- If a future step genuinely needs a real database, it builds its own engine
  and sessionmaker inside the fixture rather than going through `get_engine()`.

Test authorship and execution belong to the `qa-backend` agent; dev agents run
only ruff, the Alembic round-trip and a boot check.
