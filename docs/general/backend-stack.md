# Backend stack

Python. What is installed, how it is arranged, and the conventions that go
with it. Architecture and layer boundaries are in
[architecture.md](architecture.md).

## Libraries

| Library | Role |
|---|---|
| **FastAPI** | HTTP API. Mounted as an app factory, `app.main:create_app` |
| **uvicorn[standard]** | ASGI server, started by `docker/entrypoint-web.sh` |
| **Pydantic v2** | Request/response schemas, camelCase aliases |
| **pydantic-settings** | The single `Settings` class in `app/core/settings.py` |
| **SQLAlchemy 2 (asyncio)** | ORM models and queries, async engine |
| **psycopg 3** | PostgreSQL driver (`postgresql+psycopg://`) |
| **Alembic** | Migrations, run by the web container's entrypoint |
| **Typer** | CLI, installed as the console script `app` |
| **argon2-cffi** | Password hashing |
| **structlog** | Structured logging to stderr |
| **LangChain / LangGraph** | The agent — not wired yet |

Dev dependencies go in **`[dependency-groups] dev`** — **pytest**, **httpx**
(for `TestClient`), **ruff** — and never in `[project.optional-dependencies]`:
`uv sync --locked` installs default dependency *groups* and no extras, so as an
extra they would be absent from the image.

Python 3.12, pinned in `backend/.python-version` and
`requires-python = ">=3.12,<3.13"`. Dependencies are declared with `>=` floors
in `backend/pyproject.toml` and resolved by the committed `backend/uv.lock`.
The build backend is `hatchling` with
`[tool.hatch.build.targets.wheel] packages = ["app"]` — required because
`uv sync --locked` installs the project and `[project.scripts]` needs a wheel.

## Layout

```
backend/
├── .python-version
├── pyproject.toml            # deps, [project.scripts], ruff, pytest
├── uv.lock
├── alembic.ini
├── alembic/{env.py, script.py.mako, versions/}
├── app/
│   ├── main.py               # create_app()
│   ├── cli.py                # `cli` Typer app
│   ├── core/                 # settings logging db errors schemas security
│   ├── api/v1/router.py      # combines module routers, nothing else
│   └── modules/<module>/     # models.py schemas.py routes.py service.py
└── tests/<module>/           # mirrors modules/ one-to-one
```

`app/core/` holds only what **two or more** modules use. A single-caller
helper lives in its caller's module.

## Conventions

### Services are modules of functions

No service classes, no repository classes, no ORM `relationship()`. A service
function takes the `AsyncSession` as its first positional argument and the
rest as keyword-only:

```python
async def create_user(db: AsyncSession, *, username: str, password: str) -> User: ...
```

Mutating functions call `await db.commit()` themselves — services own the
transaction boundary. `get_db_session` yields the session and rolls back on
exception; it never commits. Routes contain no `commit`, no `add`, no
`execute`.

Because the test suite is authored against them before the implementation
exists, exported service function names and signatures are **contract**, pinned
in the step spec, and changing one is a spec amendment.

### Sessions and the engine

`app/core/db.py` holds `Base`, `get_engine()`, `get_sessionmaker()`,
`get_db_session()` and the `DbSession = Annotated[AsyncSession,
Depends(get_db_session)]` alias. The two accessors are `@lru_cache`d and are
called **only** from `get_db_session` — never at import time, never from a
lifespan handler. The cache is keyed process-wide rather than per event loop,
so an engine built outside the serving loop breaks async tests; see
`.claude/skills/qa-checklist/SKILL.md`.

### Schemas

Every request and response model derives from the shared camelCase base in
`app/core/schemas.py`:

```python
class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
```

FastAPI serialises response models by alias, so responses are camelCase with
no mapping code.

Schema class names become OpenAPI component names and route function names
become `operationId`s, both of which the committed
`frontend/src/api/schema.d.ts` depends on. Route functions therefore carry
**no docstrings** and fields carry no `description=`: explanatory prose goes
in a `#` comment above the decorator, so the exported schema stays stable.
Each route declares its failure `responses=` explicitly.

### Errors

`app/core/errors.py` holds the `ErrorCode` values, the `ApiError` exception and
`register_error_handlers(app)`, which installs four handlers:
`ApiError`, `RequestValidationError` (→ `422 VALIDATION_ERROR` with
`details.fields`), Starlette's `HTTPException` (→ `404`/`405` in the envelope)
and a catch-all `Exception` (→ `500 INTERNAL_ERROR`, traceback logged, nothing
leaked). The envelope is described in [architecture.md](architecture.md).

Raise `ApiError` from services, not `HTTPException` from routes. The
`ApiError` handler is also what clears the session cookie on
`SESSION_EXPIRED`: a dependency that raises has its injected `Response`
discarded, so `require_auth` cannot do it itself. Routes and dependencies never
construct a `Response` — they take `response: Response`, set cookies and
headers on it, and return the model or `None`, which FastAPI merges even into a
bodiless `204`.

### Logging

`configure_logging()` in `app/core/logging.py` sets up structlog writing to
**stderr** — `ConsoleRenderer` in development, `JSONRenderer` otherwise, level
from `LOG_LEVEL`. Called once from `create_app()` and once from the CLI entry
point. Stdout is reserved for command output so
`app openapi export > frontend/openapi.json` produces valid JSON.

Never log a password, a session token or a CSRF token.

### Security primitives

`app/core/security.py` is the only place that touches cryptography:
`hash_password` / `verify_password` (Argon2, `PasswordHasher()` with library
defaults — no tuning, no rehash-on-verify), `generate_token`
(`secrets.token_urlsafe(32)`), `hash_token` (hex SHA-256) and `tokens_equal`
(`secrets.compare_digest`). It is in `core/` because both `users` and `auth`
call it.

## Migrations

`alembic.ini` sets `script_location = alembic`, `prepend_sys_path = .`,
`file_template = %%(rev)s_%%(slug)s`, and leaves `sqlalchemy.url` empty:
`alembic/env.py` takes the URL from `get_settings().database_url`, so there is
one source of truth. Online migrations run through `create_async_engine` and
`connection.run_sync`.

`env.py` imports each module's models explicitly for
`target_metadata = Base.metadata`:

```python
from app.modules.auth import models as auth_models   # noqa: F401
from app.modules.users import models as users_models  # noqa: F401
```

A new module adds one line. There is no autodiscovery.

Every migration must round-trip: `upgrade head` → `downgrade base` →
`upgrade head` against a fresh database. `downgrade()` drops in reverse
dependency order. The web container runs `alembic upgrade head` on every boot,
so a migration that fails takes the API down — verify the round-trip before
landing.

## CLI

`app/cli.py` exposes `cli = typer.Typer()`, registered in `pyproject.toml` as

```toml
[project.scripts]
app = "app.cli:cli"
```

so the command inside the container is `app`. Commands are grouped into
sub-apps: `app openapi export` prints the OpenAPI document to stdout, which is
what `make generate-api` redirects into `frontend/openapi.json`. A command
that produces data writes **only** that data to stdout.

Use the CLI for anything that is not a request: seeding, ingestion, one-off
maintenance. There is no job runner to use instead.

## Configuration

One `Settings` class, reached through `@lru_cache def get_settings()`. Only
what the code actually reads is declared; `extra="ignore"` means extra keys in
`.env` are harmless, so `.env.dist` may document variables a later phase will
use. Never read `os.environ` outside `settings.py`.

## Tooling

```bash
# from backend/, after `uv sync`
uv run ruff check .           # lint
uv run ruff format --check .  # formatting (drop --check to apply)
uv run pytest                 # tests

# or, Docker-only, works with the stack down
make backend-lint
make backend-test
```

Ruff config lives in `[tool.ruff]` in `pyproject.toml`: line length 100,
target `py312`, rule sets `E F I UP B SIM ASYNC`.

Pytest config lives in `[tool.pytest.ini_options]`: `testpaths = ["tests"]`,
**`filterwarnings = ["error"]`** — a warning fails the suite.

### Test arrangement

The suite is fully synchronous and never constructs a database engine:

- `tests/conftest.py` pins the environment variables before the app is
  imported and calls `get_settings.cache_clear()`, so the root `.env` cannot
  influence a run.
- Tests drive the app with `fastapi.testclient.TestClient`, and the CLI with
  Typer's `CliRunner`. There is no `pytest-asyncio` and there are no async
  fixtures.
- `app.dependency_overrides[get_db_session]` returns a stub; route tests
  monkeypatch the pinned service functions. The engine accessors are therefore
  never called and never need `cache_clear()`. This works only because routes
  and dependencies hold a **module** reference — `from . import service`, or
  `from app.modules.users import service as users_service` across modules — and
  call `service.create_user(...)`. Importing a service function by name
  (`from .service import create_user`) rebinds it into the route module and the
  monkeypatch silently misses.
- Pure functions (username normalisation, hashing, token helpers) are tested
  directly.
- To observe the 500 envelope, use `TestClient(app,
  raise_server_exceptions=False)` — Starlette otherwise re-raises server
  exceptions into the test.

If a future step genuinely needs a real database in tests, it builds its own
engine and sessionmaker inside the fixture rather than going through
`get_engine()` / `get_sessionmaker()`.

Test authorship and execution belong to the `qa-backend` agent; dev agents run
only ruff, the Alembic round-trip and a boot check.
