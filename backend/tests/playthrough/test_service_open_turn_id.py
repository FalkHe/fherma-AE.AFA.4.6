"""WI1 (sprint 010/03): `open_turn_id` -- the run's open turn id, read back
from `events` alone, for `game.service.run_turn` to reuse across a
resumed interrupt leg (I3).

Engine-free (`FakeSession`/`FakeResult`, the same shape `test_recap.py`
uses): `execute()` returns queued results in call order -- the membership
lookup first, then the turn id read.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio

import pytest

from app.core.ids import generate_id
from app.modules.playthrough import service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.playthrough.models import CampaignRunMember

RUN_ID = generate_id()
USER_ID = generate_id()


class FakeResult:
    def __init__(self, *, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    """Engine-free stand-in for `AsyncSession`. `execute()` returns the
    queued results in order: the membership lookup first, then (only when
    the caller is a member) the turn id read."""

    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _stmt):
        return self._results.pop(0)


def test_a_caller_not_seated_at_the_run_is_refused_before_any_turn_id_read():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError) as exc_info:
        asyncio.run(service.open_turn_id(db, user_id=USER_ID, run_id=RUN_ID))

    assert exc_info.value.run_id == RUN_ID


def test_no_open_turn_reports_none():
    """Covers both a run with no event yet and a newest event written with
    no `turn_id` at all -- indistinguishable at this call's own read, a
    single `NULL` column value either way."""
    member = CampaignRunMember(campaign_run_id=RUN_ID, user_id=USER_ID)
    db = FakeSession(FakeResult(scalar=member), FakeResult(scalar=None))

    result = asyncio.run(service.open_turn_id(db, user_id=USER_ID, run_id=RUN_ID))

    assert result is None


def test_returns_the_newest_events_own_turn_id():
    member = CampaignRunMember(campaign_run_id=RUN_ID, user_id=USER_ID)
    turn_id = generate_id()
    db = FakeSession(FakeResult(scalar=member), FakeResult(scalar=turn_id))

    result = asyncio.run(service.open_turn_id(db, user_id=USER_ID, run_id=RUN_ID))

    assert result == turn_id
