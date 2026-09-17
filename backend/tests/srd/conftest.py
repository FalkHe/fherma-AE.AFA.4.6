"""`srd_db`: a real, migrated scratch Postgres database for `tests/srd`'s
`@pytest.mark.database` tests, pinned to the `1536` embedding width the
`0002_srd_rules` migration hard-codes for its `vector` column -- unrelated
to `tests/conftest.py`'s suite-wide `4` pin, which stays untouched for
every test outside this directory. The generic lifecycle (reachability
probe, scratch-database creation, the subprocess `alembic upgrade head`,
the engine/session, teardown and environment restore) lives in
`tests/database.py`'s `scratch_db`, shared by every suite that needs a real
database."""

import pytest

from tests.database import scratch_db


@pytest.fixture
def srd_db():
    yield from scratch_db(EMBEDDING_DIMENSIONS="1536")
