"""`srd_db`: a real, migrated scratch Postgres database for `tests/srd`'s
`@pytest.mark.database` tests (WI4, sprint 004/01's harness work item).

Skips cleanly (`pytest.skip`) when no Postgres server answers, so `make
backend-test` (`--no-deps`, per `AGENTS.md`) stays green whether or not the
dev `postgres` service happens to be running. When one does answer, the
fixture:

1. creates a scratch *database* (never a schema) named `srd_test_<hex>` --
   `CREATE EXTENSION` is per-database, and the dev `application` database
   must never gain rows from a test run;
2. pins `DATABASE_URL` to it and `EMBEDDING_DIMENSIONS` to `1536` (the
   migration's fixed vector width -- unrelated to `tests/conftest.py`'s
   suite-wide `4` pin, which stays untouched for every test outside this
   directory), clearing `get_settings()`'s cache both times;
3. runs `alembic upgrade head` **as a subprocess**, not in-process: `env.py`
   calls `fileConfig()`, which would otherwise re-configure the logging
   module against the autouse structlog guard in `tests/conftest.py`. A
   subprocess inherits the pinned env vars (`DATABASE_URL` first, `env.py`
   reads it via `get_settings()` at run time) but has its own, disposable
   logging config;
4. yields an `AsyncSession` bound to its own `create_async_engine` -- never
   the app's cached `get_engine()`/`get_sessionmaker()`, which are pinned to
   `DATABASE_URL` at first call and must never see the scratch database;
5. tears down: closes the session and disposes the engine, restores the
   environment (and the settings cache) exactly as found, then drops the
   scratch database with `WITH (FORCE)` so a still-open connection from a
   failed test never leaves it behind.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every test wraps
its own async calls in a single `asyncio.run(...)`; only the teardown here
does the same for `session.close()` / `engine.dispose()`."""

import asyncio
import os
import subprocess
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.settings import get_settings

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# Matches `DATABASE_URL` in `.env.dist` / `tests/conftest.py`'s pin -- the
# "postgres" Compose service, reached by its service name on the shared
# Docker network. Used only as a fallback if `DATABASE_URL` is somehow unset;
# `tests/conftest.py` always sets it before this module is ever imported.
_DEFAULT_ADMIN_URL = "postgresql+psycopg://app:app@postgres:5432/application"

# Width the migration hard-codes (`SrdRule.EMBEDDING_WIDTH` /
# `0002_srd_rules.py`), independent of `tests/conftest.py`'s suite-wide `4`.
_MIGRATED_VECTOR_WIDTH = "1536"


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


@pytest.fixture
def srd_db():
    admin_url = os.environ.get("DATABASE_URL", _DEFAULT_ADMIN_URL)

    if not _server_reachable(admin_url):
        pytest.skip("no reachable Postgres server")

    scratch_name = f"srd_test_{uuid.uuid4().hex[:16]}"
    scratch_url = _with_database(admin_url, scratch_name)

    with psycopg.connect(_psycopg_conninfo(admin_url), autocommit=True) as admin_conn:
        admin_conn.execute(f'CREATE DATABASE "{scratch_name}"')

    old_database_url = os.environ.get("DATABASE_URL")
    old_embedding_dimensions = os.environ.get("EMBEDDING_DIMENSIONS")
    os.environ["DATABASE_URL"] = scratch_url
    os.environ["EMBEDDING_DIMENSIONS"] = _MIGRATED_VECTOR_WIDTH
    get_settings.cache_clear()

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
        if old_embedding_dimensions is None:
            os.environ.pop("EMBEDDING_DIMENSIONS", None)
        else:
            os.environ["EMBEDDING_DIMENSIONS"] = old_embedding_dimensions
        get_settings.cache_clear()

        with psycopg.connect(_psycopg_conninfo(admin_url), autocommit=True) as admin_conn:
            admin_conn.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
