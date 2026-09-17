"""`scratch_db` (`tests/database.py`), sprint 003/01 WI1: the shared
scratch-database generator itself, not any one module's use of it.

Marked `database` throughout except the unreachable-server case, which
never needs a real Postgres and stays fast and unmarked so it always runs
under `make backend-test` (`--no-deps`)."""

import asyncio
import os

import psycopg
import pytest
from sqlalchemy import text

from tests import database


def test_ac_skips_when_no_server_answers(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:app@127.0.0.1:1/nope")

    gen = database.scratch_db()
    with pytest.raises(pytest.skip.Exception):
        next(gen)


@pytest.mark.database
def test_ac_creates_uniquely_named_database():
    names = []
    for _ in range(2):
        gen = database.scratch_db()
        next(gen)
        scratch_url = os.environ["DATABASE_URL"]
        names.append(scratch_url.rsplit("/", 1)[-1])
        gen.close()

    first, second = names
    assert first != second
    assert all(name.startswith("test_") for name in names)


@pytest.mark.database
def test_ac_applies_every_migration():
    async def _inspect(session):
        tables = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name IN ('users', 'srd_rules')"
            )
        )
        return {row[0] for row in tables}

    gen = database.scratch_db()
    session = next(gen)
    try:
        found = asyncio.run(_inspect(session))
        assert found == {"users", "srd_rules"}
    finally:
        gen.close()


@pytest.mark.database
def test_ac_yields_a_working_session():
    async def _select_one(session):
        result = await session.execute(text("SELECT 1"))
        return result.scalar()

    gen = database.scratch_db()
    session = next(gen)
    try:
        assert asyncio.run(_select_one(session)) == 1
    finally:
        gen.close()


@pytest.mark.database
def test_ac_teardown_closes_session_and_restores_pinned_env_vars():
    admin_database_url = os.environ["DATABASE_URL"]
    os.environ["SCRATCH_DB_PRESENT_PIN"] = "before"
    os.environ.pop("SCRATCH_DB_ABSENT_PIN", None)

    gen = database.scratch_db(SCRATCH_DB_PRESENT_PIN="during", SCRATCH_DB_ABSENT_PIN="during")
    session = next(gen)
    assert os.environ["DATABASE_URL"] != admin_database_url
    assert os.environ["SCRATCH_DB_PRESENT_PIN"] == "during"
    assert os.environ["SCRATCH_DB_ABSENT_PIN"] == "during"

    gen.close()

    assert os.environ["DATABASE_URL"] == admin_database_url
    assert os.environ["SCRATCH_DB_PRESENT_PIN"] == "before"
    assert "SCRATCH_DB_ABSENT_PIN" not in os.environ

    with pytest.raises(Exception):  # noqa: B017 - closed session/disposed engine, driver-specific
        asyncio.run(session.execute(text("SELECT 1")))

    os.environ.pop("SCRATCH_DB_PRESENT_PIN", None)


@pytest.mark.database
def test_ac_drops_database_even_after_a_failure():
    admin_database_url = os.environ["DATABASE_URL"]

    class _Boom(Exception):
        pass

    gen = database.scratch_db()
    next(gen)
    scratch_name = os.environ["DATABASE_URL"].rsplit("/", 1)[-1]

    with pytest.raises(_Boom):
        gen.throw(_Boom())

    assert os.environ["DATABASE_URL"] == admin_database_url

    conninfo = database._psycopg_conninfo(admin_database_url)
    with psycopg.connect(conninfo, autocommit=True) as admin_conn:
        result = admin_conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (scratch_name,))
        assert result.fetchone() is None
