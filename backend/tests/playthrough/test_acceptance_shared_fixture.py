"""Acceptance test for AC2 -- sprint 003/01 "one scratch-database fixture,
shared"
(`docs/intents/003-game-state/sprints/01-shared-database-fixture/brief.md`).

Consumes `playthrough_db` (`tests/playthrough/conftest.py`) exactly as any
future test in this package would -- as a plain pytest fixture, never
driving the underlying `scratch_db` generator directly (that is
`test_shared_scratch_database.py`'s job, against AC1). This package owns no
migration of its own, so a real `srd_rules` table proves the whole chain
ran for it anyway, through the shared helper alone.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): the async call is
wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy import text


@pytest.mark.database
def test_ac2_playthrough_db_answers_a_query_against_a_fully_migrated_database(playthrough_db):
    # <- AC2: the session works at all (a trivial `SELECT 1`), and the SRD
    # migration's table exists even though `playthrough` defines none of
    # its own -- proof that `alembic upgrade head` ran the full chain, not
    # just some module-local slice of it.
    async def _inspect():
        answer = await playthrough_db.execute(text("SELECT 1"))
        assert answer.scalar() == 1

        table = await playthrough_db.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_name = 'srd_rules'")
        )
        assert table.scalar() == "srd_rules"

    asyncio.run(_inspect())
