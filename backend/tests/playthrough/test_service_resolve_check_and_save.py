"""WI1 (sprint 07b): turning a roll into pass or fail, and spending it
exactly once -- AC3.

qa's own `test_acceptance_rolls_spent_once.py` drives the black-box happy
path and refusals against the sprint's interface contracts; this file
covers what that suite does not: the gate order these two consumers share
with every other mechanic (an unknown roll id, a foreign run, an archived
run, an invalid status), and the private `_consume_roll` directly -- in
particular the "belongs to this game" branch no caller of
`resolve_check`/`resolve_save` alone can ever reach, since both derive
their own run from the roll they are given.

Gates are engine-free (`FakeSession`, the same shape
`test_service_use_exit.py` and `test_service_rolls.py` use); everything
that needs a real roll, a real refusal record, or a real re-read is
`@pytest.mark.database`.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.playthrough import dice, service
from app.modules.playthrough.errors import (
    CampaignRunNotFoundError,
    InvalidDcError,
    InvalidRunStatusError,
    RollNotFoundError,
    RollNotUsableError,
    RunArchivedError,
)
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, Event

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _new_character(db, *, user_id: str):
    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id)
    return run, character


async def _event_row(db, event_id: str):
    return (
        await db.execute(
            text("SELECT type, visibility, payload, turn_id FROM events WHERE id = :id"),
            {"id": event_id},
        )
    ).one()


async def _make_roll(
    db, *, user_id: str, actor_id: str, kind: str = "ability_check", turn_id: str | None = None
):
    from collections.abc import Iterator

    class _ScriptedRandom:
        def __init__(self, values: Iterator[int]):
            self._values = values

        def randint(self, a: int, b: int) -> int:
            return next(self._values)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dice, "_rng", lambda: _ScriptedRandom(iter([10])))
        context = {"expression": "1d1"} if kind == "custom" else {"ability": "wisdom"}
        return await service.roll(
            db,
            user_id=user_id,
            actor_id=actor_id,
            kind=kind,
            context=context,
            visibility="player",
            turn_id=turn_id,
        )


# --- gates, engine-free (FakeSession, `test_service_use_exit.py`'s shape) -


class FakeResult:
    def __init__(self, *, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, *results):
        self._results = list(results)
        self.added: list[object] = []
        self.committed = 0

    async def execute(self, stmt):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed += 1


def _roll_event(event_id="roll-1", *, campaign_run_id="run-1", kind="ability_check", turn_id=None):
    return Event(
        id=event_id,
        campaign_run_id=campaign_run_id,
        type="roll",
        visibility="player",
        turn_id=turn_id,
        payload={"kind": kind, "actorId": "actor-1", "formula": "1d20", "faces": [10],
                 "modifier": 0, "total": 10},
    )


def _member(run_id="run-1", user_id="user-1"):
    return CampaignRunMember(campaign_run_id=run_id, user_id=user_id, role="owner")


def _run(run_id="run-1", *, status="ready"):
    return CampaignRun(id=run_id, campaign_id=CAMPAIGN_ID, content_version=VERSION, status=status)


def test_resolve_check_raises_roll_not_found_for_an_unknown_roll_id():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(RollNotFoundError):
        asyncio.run(service.resolve_check(db, user_id="user-1", roll_id="no-such-roll", dc=10))
    assert db.added == []
    assert db.committed == 0


def test_resolve_check_raises_roll_not_found_for_an_event_that_is_not_a_roll():
    from app.modules.playthrough.models import Event as _Event

    other = _Event(
        id="event-1", campaign_run_id="run-1", type="question", visibility="player",
        payload={"text": "Well?", "options": []},
    )
    db = FakeSession(FakeResult(scalar=other))

    with pytest.raises(RollNotFoundError):
        asyncio.run(service.resolve_check(db, user_id="user-1", roll_id="event-1", dc=10))
    assert db.committed == 0


def test_resolve_save_raises_campaign_run_not_found_for_a_roll_on_a_foreign_run():
    db = FakeSession(FakeResult(scalar=_roll_event()), FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(service.resolve_save(db, user_id="user-1", roll_id="roll-1", dc=10))
    assert db.added == []
    assert db.committed == 0


def test_resolve_check_raises_run_archived_for_an_archived_run():
    db = FakeSession(
        FakeResult(scalar=_roll_event()),
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run(status="archived")),
    )

    with pytest.raises(RunArchivedError):
        asyncio.run(service.resolve_check(db, user_id="user-1", roll_id="roll-1", dc=10))
    assert db.committed == 0


@pytest.mark.parametrize("status", ["setup", "finished"])
def test_resolve_check_raises_invalid_run_status_outside_ready_or_active(status):
    db = FakeSession(
        FakeResult(scalar=_roll_event()),
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run(status=status)),
    )

    with pytest.raises(InvalidRunStatusError):
        asyncio.run(service.resolve_check(db, user_id="user-1", roll_id="roll-1", dc=10))
    assert db.committed == 0


# --- `_consume_roll` directly, engine-free ---------------------------------


def test_consume_roll_raises_roll_not_found_for_a_roll_belonging_to_another_game():
    # <- the branch no caller of resolve_check/resolve_save alone can ever
    # reach, since both derive their own run from the roll they are given;
    # a future consumer (08/09) may know its run independently.
    db = FakeSession(FakeResult(scalar=_roll_event(campaign_run_id="run-1")))

    with pytest.raises(RollNotFoundError):
        asyncio.run(
            service._consume_roll(
                db, run_id="a-different-run", roll_id="roll-1", kind="ability_check", turn_id=None
            )
        )


# --- the real thing: pass, fail, and each refusal, against a real database -


@pytest.mark.database
def test_resolve_check_passes_and_appends_the_outcome_on_the_spending_entry(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-check-pass")
        await playthrough_db.commit()
        run, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(playthrough_db, user_id=user_id, actor_id=character.id)
        assert rolled.payload["total"] == 10

        success = await service.resolve_check(
            playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10
        )
        assert success is True

        roll_row = await _event_row(playthrough_db, rolled.id)
        assert roll_row.type == "roll"
        assert "success" not in roll_row.payload  # ← D11: never on the roll itself

        row = (
            await playthrough_db.execute(
                text(
                    "SELECT visibility, payload FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call' ORDER BY id DESC LIMIT 1"
                ),
                {"run_id": run.id},
            )
        ).one()
        assert row.visibility == "dm"
        assert row.payload["name"] == "resolve_check"
        assert row.payload["args"] == {"rollId": rolled.id, "dc": 10}
        assert row.payload["rollIds"] == [rolled.id]
        assert row.payload["result"] == "ok"
        assert row.payload["outcome"] == {"total": 10, "dc": 10, "success": True}

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_save_fails_when_the_total_is_below_the_dc(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-save-fail")
        await playthrough_db.commit()
        _, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(
            playthrough_db, user_id=user_id, actor_id=character.id, kind="saving_throw"
        )

        success = await service.resolve_save(
            playthrough_db, user_id=user_id, roll_id=rolled.id, dc=rolled.payload["total"] + 1
        )
        assert success is False

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_check_refuses_a_custom_roll_and_the_roll_stays_recorded(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-check-custom")
        await playthrough_db.commit()
        run, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(
            playthrough_db, user_id=user_id, actor_id=character.id, kind="custom"
        )

        with pytest.raises(RollNotUsableError) as excinfo:
            await service.resolve_check(playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10)
        assert excinfo.value.code == ErrorCode.ROLL_NOT_USABLE

        refused = (
            await playthrough_db.execute(
                text(
                    "SELECT visibility, payload FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call' ORDER BY id"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(refused) == 1
        assert refused[0].visibility == "dm"
        assert refused[0].payload["name"] == "resolve_check"
        assert refused[0].payload["result"] == "refused"
        assert refused[0].payload["rollIds"] == []

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_check_refuses_a_roll_from_another_turn(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-check-turn")
        await playthrough_db.commit()
        _, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(
            playthrough_db, user_id=user_id, actor_id=character.id, turn_id=generate_id()
        )

        with pytest.raises(RollNotUsableError):
            await service.resolve_check(
                playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10, turn_id=None
            )

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_check_refuses_a_dc_outside_five_to_thirty(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-check-dc")
        await playthrough_db.commit()
        run, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(playthrough_db, user_id=user_id, actor_id=character.id)

        with pytest.raises(InvalidDcError) as excinfo:
            await service.resolve_check(playthrough_db, user_id=user_id, roll_id=rolled.id, dc=4)
        assert excinfo.value.code == ErrorCode.INVALID_DC

        refused = (
            await playthrough_db.execute(
                text(
                    "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call'"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(refused) == 1
        assert refused[0].payload["result"] == "refused"
        assert refused[0].payload["args"] == {"rollId": rolled.id, "dc": 4}

        # <- the roll is still untouched by any successful spend.
        with pytest.raises(InvalidDcError):
            await service.resolve_check(playthrough_db, user_id=user_id, roll_id=rolled.id, dc=31)

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_check_refuses_a_roll_already_spent_by_a_prior_successful_call(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-check-twice")
        await playthrough_db.commit()
        _, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(playthrough_db, user_id=user_id, actor_id=character.id)

        first = await service.resolve_check(
            playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10
        )
        assert first is True

        with pytest.raises(RollNotUsableError):
            await service.resolve_check(playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10)

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_refused_attempt_leaves_the_roll_still_spendable_afterwards(playthrough_db):
    # <- the subtle clause: only a *successful* spend burns the roll, so a
    # refusal (here, a dc out of range) must not stop a later, valid call
    # from spending the same roll.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-check-refusal-then-ok")
        await playthrough_db.commit()
        _, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(playthrough_db, user_id=user_id, actor_id=character.id)

        with pytest.raises(InvalidDcError):
            await service.resolve_check(playthrough_db, user_id=user_id, roll_id=rolled.id, dc=3)

        success = await service.resolve_check(
            playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10
        )
        assert success is True

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_check_refuses_a_saving_throw_roll_kind_mismatch(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-check-kind-mismatch")
        await playthrough_db.commit()
        _, character = await _new_character(playthrough_db, user_id=user_id)

        rolled = await _make_roll(
            playthrough_db, user_id=user_id, actor_id=character.id, kind="saving_throw"
        )

        with pytest.raises(RollNotUsableError):
            await service.resolve_check(playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10)

        # <- the same roll, asked of the mechanic it actually matches,
        # still spends normally -- the earlier refusal did not touch it.
        success = await service.resolve_save(
            playthrough_db, user_id=user_id, roll_id=rolled.id, dc=10
        )
        assert success is True

    asyncio.run(_scenario())

