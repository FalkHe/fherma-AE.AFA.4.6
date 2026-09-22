"""WI2 (sprint 006/02): `recap` (`service.py`) -- a run's newest `n`
narration events, returned oldest first, with no question asked (AC2, AC4).

Engine-free, same `FakeSession`/`FakeResult` shape `test_run_cost.py` uses:
`execute()` returns queued results in call order -- `recap`'s own
`_get_run` lookup first, then the narration rows. `FakeResult.all()` hands
back the newest-first rows the `ORDER BY id DESC LIMIT n` would pick; the
service is what flips them to chronological order, so a test that queues
already-chronological rows and asserts nothing would prove nothing.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from datetime import UTC, datetime

import pytest

from app.core.ids import generate_id
from app.modules.playthrough import service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.playthrough.models import CampaignRun
from app.modules.playthrough.schemas import NarrationRead


class FakeResult:
    """Stands in for the object `AsyncSession.execute()` returns -- either
    a single scalar (`_get_run`'s lookup) or a list of narration rows,
    never both."""

    def __init__(self, *, scalar=None, rows=()):
        self._scalar = scalar
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows


class FakeSession:
    """Engine-free stand-in for `AsyncSession`. `execute()` returns the
    queued results in order: the run lookup first, then (only when the
    run exists) the narration rows."""

    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _stmt):
        return self._results.pop(0)


RUN_ID = generate_id()


def _boom_embed_texts(*args, **kwargs):
    raise AssertionError("recap must never call the embedding seam")


def test_ac4_an_unknown_run_raises_not_found_before_any_narration_query(monkeypatch):
    monkeypatch.setattr(service.llm_service, "embed_texts", _boom_embed_texts)
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError) as exc_info:
        asyncio.run(service.recap(db, run_id=RUN_ID, n=5))

    assert exc_info.value.run_id == RUN_ID


def test_ac2_returns_the_newest_n_in_chronological_order_with_no_embedding_call(monkeypatch):
    monkeypatch.setattr(service.llm_service, "embed_texts", _boom_embed_texts)
    run = CampaignRun(id=RUN_ID, campaign_id="greenhollow", content_version="v1")

    created = [datetime(2024, 1, 1, hour, tzinfo=UTC) for hour in range(1, 4)]
    # Queued newest-first, exactly as `ORDER BY id DESC LIMIT n` would hand
    # them back -- three rows though only two are asked for, so the
    # oldest of the three is never even in the picture.
    rows = [
        ("evt-3", created[2], {"text": "third"}),
        ("evt-2", created[1], {"text": "second"}),
    ]
    db = FakeSession(FakeResult(scalar=run), FakeResult(rows=rows))

    result = asyncio.run(service.recap(db, run_id=RUN_ID, n=2))

    assert result == [
        NarrationRead(id="evt-2", created_at=created[1], text="second"),
        NarrationRead(id="evt-3", created_at=created[2], text="third"),
    ]


def test_ac4_a_run_with_no_narration_returns_nothing(monkeypatch):
    monkeypatch.setattr(service.llm_service, "embed_texts", _boom_embed_texts)
    run = CampaignRun(id=RUN_ID, campaign_id="greenhollow", content_version="v1")
    db = FakeSession(FakeResult(scalar=run), FakeResult(rows=[]))

    result = asyncio.run(service.recap(db, run_id=RUN_ID))

    assert result == []
