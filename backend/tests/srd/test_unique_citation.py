"""WI1 (sprint 04): the store refuses a duplicate citation rather than
trusting the splitter (AC2) -- `0003_srd_rules_unique_citation`'s unique
constraint on `(source_version, heading_path, ordinal)`, exercised against a
real, migrated database.

Marked `database`, so it is collected but skipped under `make
backend-test` (`--no-deps`, no reachable Postgres by design) and actually
run for real under `make backend-test-db`, mirroring
`test_database_harness.py`.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): the async insert is
wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule


def _row(*, source_version="v1", heading_path="Spells › Fire Bolt", ordinal=0, text="a passage"):
    return SrdRule(
        source_version=source_version,
        heading_path=heading_path,
        ordinal=ordinal,
        text=text,
        token_count=3,
        embedding_model="text-embedding-3-small",
        embedding=[0.0] * EMBEDDING_WIDTH,
    )


@pytest.mark.database
def test_database_rejects_a_duplicate_source_version_heading_path_ordinal(srd_db):
    async def _insert_both():
        srd_db.add(_row())
        await srd_db.commit()

        srd_db.add(_row(text="a different passage claiming the same citation"))
        with pytest.raises(IntegrityError):
            await srd_db.commit()
        await srd_db.rollback()

    asyncio.run(_insert_both())


@pytest.mark.database
def test_database_allows_the_same_heading_path_at_a_different_ordinal(srd_db):
    async def _insert_both():
        srd_db.add(_row(ordinal=0))
        srd_db.add(_row(ordinal=1, text="the next passage under the same heading"))
        await srd_db.commit()

    asyncio.run(_insert_both())
