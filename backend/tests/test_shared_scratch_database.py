"""Acceptance tests for AC1 -- sprint 003/01 "one scratch-database fixture,
shared"
(`docs/intents/003-game-state/sprints/01-shared-database-fixture/brief.md`).

`scratch_db` (`tests/database.py`) is a plain generator, not a pytest
fixture -- every test here drives it directly with `next()` / `close()` /
`throw()`, exactly as its own callers (`tests/srd/conftest.py`'s `srd_db`,
`tests/playthrough/conftest.py`'s `playthrough_db`) do via `yield from`.
Marked `database` except the unreachable-server case: that one proves its
point with a deliberately bad `DATABASE_URL` and never needs a real
Postgres, so it stays unmarked and keeps running under `make backend-test`
(`--no-deps`) rather than being skipped alongside the rest. Every other
test here is real-database-backed and skips cleanly there, running for
real under `make backend-test-db`.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call is
wrapped in a single `asyncio.run(...)`.
"""

import asyncio
import os
import re

import psycopg
import pytest
from sqlalchemy import text

from tests.database import scratch_db

_SCRATCH_NAME_PATTERN = re.compile(r"^test_[0-9a-f]{16}$")


def _psycopg_conninfo(sqlalchemy_url: str) -> str:
    """`postgresql+psycopg://...` -> the plain `postgresql://...` conninfo
    `psycopg.connect` accepts -- mirrors `tests/srd/conftest.py`'s helper of
    the same name; this file never imports that fixture's own private
    helpers, only the public `scratch_db` seam."""
    scheme, _, rest = sqlalchemy_url.partition("://")
    bare_scheme = scheme.split("+", 1)[0]
    return f"{bare_scheme}://{rest}"


def _database_exists(admin_url: str, name: str) -> bool:
    with psycopg.connect(_psycopg_conninfo(admin_url), autocommit=True) as conn:
        result = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
        return result.fetchone() is not None


def test_ac1_skips_cleanly_when_no_server_answers(monkeypatch):
    # <- AC1: an unreachable admin server produces a `pytest.skip`, not an
    # error bubbling out of the generator -- the thing that keeps `make
    # backend-test` (`--no-deps`) green with no Postgres in the picture.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:app@127.0.0.1:1/nope")

    gen = scratch_db()
    with pytest.raises(pytest.skip.Exception):
        next(gen)


@pytest.mark.database
def test_ac1_creates_a_database_named_test_plus_a_hex_suffix():
    # <- AC1: the scratch database itself, not just its URL, is named
    # `test_<hex>` -- checked against the real `pg_database` catalog.
    admin_url = os.environ["DATABASE_URL"]

    gen = scratch_db()
    try:
        next(gen)
        scratch_name = os.environ["DATABASE_URL"].rsplit("/", 1)[-1]

        assert _SCRATCH_NAME_PATTERN.match(scratch_name), scratch_name
        assert _database_exists(admin_url, scratch_name)
    finally:
        gen.close()


@pytest.mark.database
def test_ac1_yields_a_session_on_a_freshly_migrated_database():
    # <- AC1: a session arrives on a database where `alembic upgrade head`
    # has actually run, proved the same way `tests/srd`'s own harness test
    # proves it for `srd_db` -- by finding a migration-created table.
    gen = scratch_db()
    try:
        session = next(gen)

        async def _inspect():
            table = await session.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_name = 'srd_rules'"
                )
            )
            assert table.scalar() == "srd_rules"

        asyncio.run(_inspect())
    finally:
        gen.close()


@pytest.mark.database
def test_ac1_pin_is_visible_while_active_and_restored_to_its_prior_value(monkeypatch):
    # <- AC1: a pin the caller passes in must actually reach the process
    # environment while the generator is active, and be put back exactly as
    # it was found once torn down -- not merely deleted.
    pin_key = "AC1_SCRATCH_DB_PROBE_PRESENT"
    monkeypatch.setenv(pin_key, "original-value")

    gen = scratch_db(**{pin_key: "probe-value"})
    next(gen)
    assert os.environ[pin_key] == "probe-value"

    gen.close()

    assert os.environ[pin_key] == "original-value"


@pytest.mark.database
def test_ac1_pin_is_removed_again_when_it_did_not_exist_before():
    # <- AC1: a pin with no prior value must be gone again afterwards, not
    # left behind with the scratch value or an empty string.
    pin_key = "AC1_SCRATCH_DB_PROBE_ABSENT"
    assert pin_key not in os.environ

    gen = scratch_db(**{pin_key: "probe-value"})
    next(gen)
    assert os.environ[pin_key] == "probe-value"

    gen.close()

    assert pin_key not in os.environ


@pytest.mark.database
def test_ac1_scratch_database_is_dropped_once_the_generator_is_exhausted():
    # <- AC1: teardown drops the scratch database -- checked against the
    # real `pg_database` catalog, not the generator's own say-so.
    admin_url = os.environ["DATABASE_URL"]

    gen = scratch_db()
    next(gen)
    scratch_name = os.environ["DATABASE_URL"].rsplit("/", 1)[-1]
    assert _database_exists(admin_url, scratch_name)

    with pytest.raises(StopIteration):
        next(gen)

    assert not _database_exists(admin_url, scratch_name)


@pytest.mark.database
def test_ac1_scratch_database_is_dropped_when_the_consuming_body_raises():
    # <- AC1: the drop must happen even when the code driving the generator
    # raises -- `gen.throw()` is how a raising consumer resumes a generator,
    # exercising the same `finally` block a `with`/`for` body would hit.
    admin_url = os.environ["DATABASE_URL"]

    class _ProbeError(Exception):
        pass

    gen = scratch_db()
    next(gen)
    scratch_name = os.environ["DATABASE_URL"].rsplit("/", 1)[-1]
    assert _database_exists(admin_url, scratch_name)

    with pytest.raises(_ProbeError):
        gen.throw(_ProbeError)

    assert not _database_exists(admin_url, scratch_name)
