"""`playthrough_db`: the same shared scratch-database helper `tests/srd`
uses (`tests/database.scratch_db`), with no keyword pins -- this module has
no schema of its own yet (sprint 003/01 adds none), so it only needs to
prove a second module reaches a real, migrated database through the shared
helper."""

import pytest

from tests.database import scratch_db


@pytest.fixture
def playthrough_db():
    yield from scratch_db()
