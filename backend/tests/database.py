"""`scratch_db`: a real, migrated scratch Postgres database for any test
suite that needs one (sprint 003/01's shared harness work item, WI1).

Generalised out of `tests/srd/conftest.py`'s former `srd_db` fixture: the
lifecycle is identical, but every environment pin beyond `DATABASE_URL`
itself is now supplied by the caller (`**env_pins`) instead of hard-coded
here -- this module carries no knowledge of any one module. `tests/srd`'s
`1536` embedding width and `vector` extension pin, for instance, stay in
that suite's own fixture, which now delegates to `scratch_db(
EMBEDDING_DIMENSIONS="1536")`.

Skips cleanly (`pytest.skip`) when no Postgres server answers, so
`make backend-test` (`--no-deps`, per `AGENTS.md`) stays green whether or
not the dev `postgres` service happens to be running. When one does
answer, the generator:

1. creates a scratch *database* (never a schema) named `test_<hex>` --
   `CREATE EXTENSION` and other database-wide state must never leak into
   the dev `application` database;
2. sets `DATABASE_URL` to the scratch URL and every `env_pins` key to its
   value, clearing `get_settings()`'s cache, then disposes and clears
   whatever `get_engine()`/`get_sessionmaker()` (`core/db.py`) may already
   have `lru_cache`d -- both are cached forever, independent of
   `DATABASE_URL`, so a stale engine left over from an earlier test (or
   from any in-process code that touches the database, e.g. a CLI command
   run the way `app playthrough cost` is) would otherwise still be pointed
   at whatever database was current when it was first built;
3. runs `alembic upgrade head` **as a subprocess**, not in-process:
   `backend/alembic/env.py` calls `fileConfig()`, which would otherwise
   re-configure the logging module against the autouse structlog guard in
   `tests/conftest.py`. A subprocess inherits the pinned env vars
   (`DATABASE_URL` first, `env.py` reads it via `get_settings()` at run
   time) but has its own, disposable logging config;
4. yields an `AsyncSession` bound to its own `create_async_engine` -- never
   the app's cached `get_engine()`/`get_sessionmaker()`. Code under test may
   still reach those (a CLI command has no request scope to hang a session
   off), and it is free to: step 2 already cleared them, so any engine
   built during the test is a fresh one bound to the scratch database;
5. tears down (even if the caller raised through the open generator):
   closes the session and disposes the engine, restores the environment
   (`DATABASE_URL` and every pinned key, popping any that were absent) and
   the settings cache exactly as found, disposes and clears the app's
   cached engine/sessionmaker again -- so nothing built during the test
   outlives the scratch database it pointed at -- then drops the scratch
   database with `WITH (FORCE)` so a still-open connection from a failed
   test never leaves it behind.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): callers wrap their
own async calls in a single `asyncio.run(...)`; only the teardown here does
the same for `session.close()` / `engine.dispose()`."""

import asyncio
import os
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db import get_engine, get_sessionmaker
from app.core.settings import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Matches `DATABASE_URL` in `.env.dist` / `tests/conftest.py`'s pin -- the
# "postgres" Compose service, reached by its service name on the shared
# Docker network. Used only as a fallback if `DATABASE_URL` is somehow unset;
# `tests/conftest.py` always sets it before this module is ever imported.
_DEFAULT_ADMIN_URL = "postgresql+psycopg://app:app@postgres:5432/application"


def _psycopg_conninfo(sqlalchemy_url: str) -> str:
    """`postgresql+psycopg://...` -> the plain `postgresql://...` conninfo
    `psycopg.connect` accepts -- it rejects the SQLAlchemy `+psycopg` driver
    tag loudly, the same fix `app/core/checkpointer/service.py`'s
    `checkpointer_conn_string` applies for the same reason."""
    scheme, _, rest = sqlalchemy_url.partition("://")
    bare_scheme = scheme.split("+", 1)[0]
    return f"{bare_scheme}://{rest}"


def _with_database(url: str, database: str) -> str:
    """`url` with its path replaced by `/database`, everything else --
    scheme, netloc, query, fragment -- left untouched."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{database}", parts.query, parts.fragment))


def _server_reachable(admin_url: str) -> bool:
    try:
        with psycopg.connect(_psycopg_conninfo(admin_url), connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


def _reset_db_engine_cache() -> None:
    """Disposes whatever `AsyncEngine` `get_engine()` currently has
    `lru_cache`d (if any), then clears both its cache and
    `get_sessionmaker()`'s.

    `get_engine()`/`get_sessionmaker()` (`core/db.py`) are cached forever,
    independent of `DATABASE_URL` -- correct in production, where the URL
    never changes mid-process, but not here: the first test that builds an
    engine in-process (e.g. a database-touching CLI command run the way
    `app playthrough cost` is) pins it to *that* test's scratch database,
    and every later test silently reuses the stale engine once its
    database has been dropped. Called both when the scratch database is
    pinned (so a stale engine from an earlier test never reaches this
    one) and again when the pins are restored on teardown (so an engine
    this test built never outlives the scratch database it pointed at).
    Disposing before dropping the cache reference matters on its own:
    `filterwarnings = ["error"]` (`pyproject.toml`) turns an undisposed
    asyncpg/psycopg engine's own warning into a failure in whatever test
    happens to run next.
    """
    if get_engine.cache_info().currsize:
        asyncio.run(get_engine().dispose())
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def scratch_db(**env_pins: str) -> Iterator[AsyncSession]:
    """Yield an `AsyncSession` on a freshly created, fully migrated scratch
    database. `env_pins` are additional `os.environ` keys (beyond
    `DATABASE_URL`, which is always pinned) the caller needs set for the
    duration -- e.g. `EMBEDDING_DIMENSIONS` for `tests/srd`. Every pin is
    restored to its prior value (or removed, if it was absent) on
    teardown, which always runs, including when the caller raises through
    the open generator."""
    admin_url = os.environ.get("DATABASE_URL", _DEFAULT_ADMIN_URL)

    if not _server_reachable(admin_url):
        pytest.skip("no reachable Postgres server")

    scratch_name = f"test_{uuid.uuid4().hex[:16]}"
    scratch_url = _with_database(admin_url, scratch_name)

    with psycopg.connect(_psycopg_conninfo(admin_url), autocommit=True) as admin_conn:
        admin_conn.execute(f'CREATE DATABASE "{scratch_name}"')

    old_database_url = os.environ.get("DATABASE_URL")
    old_pins = {key: os.environ.get(key) for key in env_pins}
    os.environ["DATABASE_URL"] = scratch_url
    for key, value in env_pins.items():
        os.environ[key] = value
    get_settings.cache_clear()
    _reset_db_engine_cache()

    engine = None
    session = None
    try:
        migration = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT,
            capture_output=True,
            text=True,
        )
        if migration.returncode != 0:
            pytest.fail(
                "alembic upgrade head failed against the scratch database:\n"
                f"{migration.stdout}\n{migration.stderr}"
            )

        engine = create_async_engine(scratch_url)
        session = async_sessionmaker(engine, expire_on_commit=False)()
        yield session
    finally:
        if session is not None:
            asyncio.run(session.close())
        if engine is not None:
            asyncio.run(engine.dispose())

        if old_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_database_url
        for key, old_value in old_pins.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value
        get_settings.cache_clear()
        _reset_db_engine_cache()

        with psycopg.connect(_psycopg_conninfo(admin_url), autocommit=True) as admin_conn:
            admin_conn.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
