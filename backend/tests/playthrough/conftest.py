"""`playthrough_db`: the same shared scratch-database helper `tests/srd`
uses (`tests/database.scratch_db`), pinned to `EMBEDDING_DIMENSIONS="1536"`
(sprint 006/02 WI1) to match `events.embedding`'s fixed width
(`EMBEDDING_WIDTH`, `models.py`) -- the same reason `tests/srd/conftest.py`
carries the same pin for its own vector column."""

import pytest

from tests.database import scratch_db


@pytest.fixture
def playthrough_db():
    yield from scratch_db(EMBEDDING_DIMENSIONS="1536")
