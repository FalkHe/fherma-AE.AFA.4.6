"""WI4: the harness itself, not the acceptance criteria that ride on it.

This is the one test this work item owns: proof that the `srd_db` fixture
(`tests/srd/conftest.py`) does what its contract promises -- a real,
migrated scratch database with the `vector` extension and the `srd_rules`
table in place. AC1/AC2/AC4 against that fixture belong to a sibling work
item (`tests/srd/test_acceptance_empty_corpus_status.py`); this file never
duplicates them.

Marked `database`, so it is collected but skipped under `make backend-test`
(`--no-deps`, no reachable Postgres by design) and actually run for real
under `make backend-test-db`."""

import asyncio

import pytest
from sqlalchemy import text


@pytest.mark.database
def test_srd_db_yields_a_migrated_database_with_the_vector_extension_and_srd_rules_table(srd_db):
    async def _inspect():
        extension = await srd_db.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert extension.scalar() == "vector"

        table = await srd_db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'srd_rules'"
            )
        )
        assert table.scalar() == "srd_rules"

    asyncio.run(_inspect())
