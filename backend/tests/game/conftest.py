"""`playthrough_db`: the same shared scratch-database helper `tests/
playthrough/conftest.py` wraps (`tests/database.scratch_db`), pinned to
`EMBEDDING_DIMENSIONS="1536"` to match `events.embedding`'s fixed width --
needed here too since a real turn through the agent writes a real
`narration` event (sprint 010/11 round 4, Fault A's concurrency test)."""

import pytest

from tests.database import scratch_db


@pytest.fixture
def playthrough_db():
    yield from scratch_db(EMBEDDING_DIMENSIONS="1536")
