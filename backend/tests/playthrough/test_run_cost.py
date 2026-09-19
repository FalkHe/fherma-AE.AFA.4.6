"""WI1 (sprint 005/05b): `run_cost` (`service.py`) -- the owner-only,
exact-decimal per-run and per-turn cost sum, and its result models
`RunCost`/`TurnCost` (`schemas.py`).

Engine-free scenarios use a small local `FakeSession`/`FakeResult` pair,
queued in call order -- `_require_member`'s lookup first, then the grouped
sum -- the same shape `tests/playthrough/test_service.py` uses for its own
`FakeSession`, but not shared with it: that file's `FakeResult` has no `all()`
and this function never touches `scalars()`.

The exact-sum scenario, ordering (`NULL` turn last) and the foreign-run
refusal are `@pytest.mark.database`, against the shared `playthrough_db`
fixture (`conftest.py`) -- a grouped `SUM` is real SQL, not something a fake
session can stand in for and still prove anything.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.core.ids import generate_id
from app.core.llm.service import Usage
from app.modules.playthrough import service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.playthrough.models import CampaignRunMember
from app.modules.playthrough.schemas import RunCost, TurnCost


class FakeResult:
    """Stands in for the object `AsyncSession.execute()` returns -- either
    a single scalar (the membership lookup) or a list of `(turn_id, total)`
    rows (the grouped sum), never both."""

    def __init__(self, *, scalar=None, rows=()):
        self._scalar = scalar
        self._rows = list(rows)

    def scalar_one_or_none(self):
        return self._scalar

    def all(self):
        return self._rows


class FakeSession:
    """Engine-free stand-in for `AsyncSession`. `execute()` returns the
    queued results in order: the membership check first, then (only when
    membership succeeds) the grouped sum."""

    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _stmt):
        return self._results.pop(0)


RUN_ID = generate_id()
USER_ID = generate_id()


def test_run_cost_checks_membership_first_like_every_other_function():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError) as exc_info:
        asyncio.run(service.run_cost(db, user_id=USER_ID, run_id=RUN_ID))

    assert exc_info.value.run_id == RUN_ID


def test_run_cost_builds_the_result_models_from_the_grouped_rows():
    member = CampaignRunMember(campaign_run_id=RUN_ID, user_id=USER_ID)
    db = FakeSession(
        FakeResult(scalar=member),
        FakeResult(
            rows=[
                ("01TURNONETURNONETURNONETU", Decimal("0.000500")),
                (None, Decimal("0.000734")),
            ]
        ),
    )

    result = asyncio.run(service.run_cost(db, user_id=USER_ID, run_id=RUN_ID))

    assert result == RunCost(
        total=Decimal("0.001234"),
        turns=[
            TurnCost(turn_id="01TURNONETURNONETURNONETU", total=Decimal("0.000500")),
            TurnCost(turn_id=None, total=Decimal("0.000734")),
        ],
    )


def test_run_cost_normalises_a_null_sum_and_an_empty_run_to_zero_not_none():
    member = CampaignRunMember(campaign_run_id=RUN_ID, user_id=USER_ID)

    # A turn whose events all carry no cost (`cost_usd` all `NULL`) sums to
    # SQL `NULL`, not `0` -- the service normalises it.
    db_null_turn = FakeSession(
        FakeResult(scalar=member),
        FakeResult(rows=[("01TURNONETURNONETURNONETU", None)]),
    )
    result = asyncio.run(service.run_cost(db_null_turn, user_id=USER_ID, run_id=RUN_ID))
    assert result.turns == [
        TurnCost(turn_id="01TURNONETURNONETURNONETU", total=Decimal("0.000000"))
    ]
    assert result.total == Decimal("0.000000")

    # A run with no events at all has no groups, and its total still reads
    # as an exact zero, never `None`.
    db_empty_run = FakeSession(FakeResult(scalar=member), FakeResult(rows=[]))
    empty_result = asyncio.run(service.run_cost(db_empty_run, user_id=USER_ID, run_id=RUN_ID))
    assert empty_result == RunCost(total=Decimal("0.000000"), turns=[])


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


@pytest.mark.database
def test_ac3_the_real_sums_group_by_turn_null_last_and_refuse_a_stranger(playthrough_db):
    # <- AC3
    async def _scenario():
        owner_id = generate_id()
        stranger_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="cost-owner")
        await _insert_user(playthrough_db, stranger_id, username="cost-stranger")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id="greenhollow"
        )

        turn_one = generate_id()
        turn_two = generate_id()

        async def _append(*, turn_id=None, cost):
            usage = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_usd=cost)
            return await service.append_event(
                playthrough_db,
                run_id=run.id,
                type="narration",
                visibility="player",
                payload={"text": "x"},
                turn_id=turn_id,
                usage=usage,
            )

        await _append(turn_id=turn_one, cost=0.0005)
        await _append(turn_id=turn_two, cost=0.0002)
        await _append(turn_id=turn_two, cost=0.0005)
        # Untagged (`turn_id=None`) events: one with no cost, one costed.
        await service.append_event(
            playthrough_db,
            run_id=run.id,
            type="narration",
            visibility="player",
            payload={"text": "untagged"},
        )
        untagged = await _append(cost=0.000034)
        assert untagged.turn_id is None
        await playthrough_db.commit()

        result = await service.run_cost(playthrough_db, user_id=owner_id, run_id=run.id)

        assert result.total == Decimal("0.001234")
        assert result.turns == [
            TurnCost(turn_id=turn_one, total=Decimal("0.000500")),
            TurnCost(turn_id=turn_two, total=Decimal("0.000700")),
            TurnCost(turn_id=None, total=Decimal("0.000034")),
        ]

        # A stranger and an unknown run are both refused identically.
        with pytest.raises(CampaignRunNotFoundError):
            await service.run_cost(playthrough_db, user_id=stranger_id, run_id=run.id)
        with pytest.raises(CampaignRunNotFoundError):
            await service.run_cost(playthrough_db, user_id=owner_id, run_id=generate_id())

    asyncio.run(_scenario())
