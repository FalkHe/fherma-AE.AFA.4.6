"""WI1 (sprint 08a): interacting with a fixture by the action its author
wrote -- AC1.

qa's own `test_acceptance_interact_and_one_action.py` drives the black-box
happy path and refusals against the sprint's interface contracts; this
file covers the gate order `interact` shares with `use_exit`/the roll
consumers (an unknown actor, an object on a foreign run), and everything
the mechanic's own checks decide: the roll path (pass and fail), the
bypass path, an unknown action, an object that is not a fixture, a
missing roll with nothing to bypass it, and a roll `_consume_roll` itself
refuses (wrong kind, already spent) -- always through 07b's one
implementation, never a second one.

Gates that need no real state are engine-free where practical; everything
that needs a real fixture, a real roll, or a real refusal record is
`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content, walking
the same path qa's own suite does: `village-green` -> `thornway` ->
`lair-maw`, where `thorn-screen` stands.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call in
one scenario is wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service
from app.modules.playthrough.errors import (
    ActionNotAvailableError,
    GameObjectNotFoundError,
    RollNotUsableError,
    RollRequiredError,
)
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, GameObject

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

LIFT_ACTION = "Lift the lashed brush aside a branch at a time, without letting it scrape on the stone"
LIFT_DC = 13
CUT_ACTION = "Cut through the lashings that hold the screen together"
CUT_DC = 10


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _ScriptedRandom:
    """Same seam `test_acceptance_rolls_spent_once.py` uses: a fixed,
    pre-scripted sequence of face values, one per call."""

    def __init__(self, faces: list[int]) -> None:
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - scripted, bounds ignored
        return self._faces.pop(0)


async def _rolled(db, *, user_id, actor_id, kind, context, face, turn_id=None):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([face]))
        return await service.roll(
            db, user_id=user_id, actor_id=actor_id, kind=kind, context=context, turn_id=turn_id
        )


class _second_connection:
    """An independent connection to the same scratch database, opened only
    after a refusing call has already raised -- proves the refusal is
    genuinely committed rather than merely flushed into the writer's own
    still-open transaction (same helper `test_acceptance_rolls_spent_
    once.py` and `test_acceptance_exits_and_endings.py` use)."""

    async def __aenter__(self):
        import os

        self._engine = create_async_engine(os.environ["DATABASE_URL"])
        sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._session = sessionmaker()
        return self._session

    async def __aexit__(self, *exc_info) -> None:
        await self._session.close()
        await self._engine.dispose()


async def _reach_lair_maw(db: AsyncSession, *, username: str):
    """A fresh run, its one character, positioned at `lair-maw` where
    `thorn-screen` stands -- two free `use_exit` calls from the entry
    scene, exactly `research.md`'s own path."""
    user_id = generate_id()
    await _insert_user(db, user_id, username=username)
    await db.commit()

    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id)
    await service.enter_adventure(db, user_id=user_id, run_id=run.id)
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-thornway")
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-lair-maw")

    fixture_id = (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = 'thorn-screen'"
            ),
            {"run_id": run.id},
        )
    ).scalar_one()

    return user_id, run, character, fixture_id


async def _tool_calls(db, run_id: str, *, result: str) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' AND visibility = 'dm' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [row.payload for row in rows if row.payload["result"] == result]


async def _object_row(db, object_id: str):
    return (
        await db.execute(
            text(
                "SELECT owner_object_id, adventure_run_id, scene_id, state "
                "FROM objects WHERE id = :id"
            ),
            {"id": object_id},
        )
    ).one()


# --- gates, engine-free -----------------------------------------------


def test_interact_raises_game_object_not_found_for_an_unknown_actor():
    class FakeResult:
        def scalar_one_or_none(self):
            return None

    class FakeSession:
        async def execute(self, stmt):
            return FakeResult()

    with pytest.raises(GameObjectNotFoundError):
        asyncio.run(
            service.interact(
                FakeSession(),
                user_id="user-1",
                actor_id="no-such-actor",
                object_id="thorn-screen-1",
                action="anything",
            )
        )


# --- the real thing -----------------------------------------------------


@pytest.mark.database
def test_interact_passes_on_an_ability_check_roll_meeting_the_dc_and_touches_no_objects(
    playthrough_db,
):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-roll-pass"
        )
        before = await _object_row(playthrough_db, fixture_id)

        # Strength +2 (score 15); a face of 11 totals exactly the dc.
        roll_event = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=11,
        )

        success = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=LIFT_ACTION,
            roll_id=roll_event.id,
        )
        assert success is True

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 1
        call = ok_calls[0]
        assert call["name"] == "interact"
        assert call["args"] == {
            "actorId": character.id,
            "objectId": fixture_id,
            "action": LIFT_ACTION,
            "rollId": roll_event.id,
        }
        assert call["rollIds"] == [roll_event.id]
        assert call["outcome"] == {
            "action": LIFT_ACTION,
            "dc": LIFT_DC,
            "total": 13,
            "success": True,
        }

        after = await _object_row(playthrough_db, fixture_id)
        assert after == before

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_records_a_failed_check_as_ok_not_a_refusal(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-roll-fail"
        )

        # Strength +2; a face of 1 totals 3, well under the dc of 13.
        roll_event = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=1,
        )

        success = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=LIFT_ACTION,
            roll_id=roll_event.id,
        )
        assert success is False

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 1
        assert ok_calls[0]["outcome"]["success"] is False
        assert ok_calls[0]["outcome"]["total"] == 3

        refused = await _tool_calls(playthrough_db, run.id, result="refused")
        assert refused == []

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_passes_with_no_roll_when_the_actor_carries_a_bypassing_item(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-bypass-pass"
        )

        knife_id = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM objects WHERE owner_object_id = :owner "
                    "AND template_id = 'shepherds-knife'"
                ),
                {"owner": character.id},
            )
        ).scalar_one()

        success = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=CUT_ACTION,
        )
        assert success is True

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 1
        call = ok_calls[0]
        assert call["args"] == {
            "actorId": character.id,
            "objectId": fixture_id,
            "action": CUT_ACTION,
        }
        assert call["rollIds"] == []
        assert call["outcome"] == {
            "action": CUT_ACTION,
            "dc": CUT_DC,
            "bypassedBy": knife_id,
            "success": True,
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_refuses_a_missing_roll_when_nothing_bypasses_it(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-roll-required"
        )
        before = await _object_row(playthrough_db, fixture_id)

        # `LIFT_ACTION` authors no `bypassed_by` at all, so no carried item
        # could ever satisfy it.
        with pytest.raises(RollRequiredError) as excinfo:
            await service.interact(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                object_id=fixture_id,
                action=LIFT_ACTION,
            )
        assert excinfo.value.code == ErrorCode.ROLL_REQUIRED

        after = await _object_row(playthrough_db, fixture_id)
        assert after == before

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused")
            assert len(refused) == 1
            assert refused[0]["name"] == "interact"
            assert refused[0]["args"] == {
                "actorId": character.id,
                "objectId": fixture_id,
                "action": LIFT_ACTION,
            }
            assert refused[0]["rollIds"] == []
            assert "reason" in refused[0]["outcome"]

        player_events = await service.list_events(playthrough_db, user_id=user_id, run_id=run.id)
        assert all(e.type != "tool_call" for e in player_events)

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_refuses_an_unknown_action(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-unknown-action"
        )

        with pytest.raises(ActionNotAvailableError) as excinfo:
            await service.interact(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                object_id=fixture_id,
                action="Push the screen over with a shoulder",
            )
        assert excinfo.value.code == ErrorCode.ACTION_NOT_AVAILABLE

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused")
            assert len(refused) == 1
            assert refused[0]["args"]["action"] == "Push the screen over with a shoulder"

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_refuses_an_object_that_is_not_a_fixture(playthrough_db):
    async def _scenario():
        user_id, run, character, _fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-not-a-fixture"
        )

        with pytest.raises(ActionNotAvailableError) as excinfo:
            await service.interact(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                object_id=character.id,  # a creature, not a fixture
                action=LIFT_ACTION,
            )
        assert excinfo.value.code == ErrorCode.ACTION_NOT_AVAILABLE

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused")
            assert len(refused) == 1
            assert refused[0]["outcome"]["reason"] == "object is not a fixture"

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_refuses_a_roll_of_the_wrong_kind(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-wrong-kind"
        )

        wrong_kind_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="initiative",
            context={},
            face=8,
        )

        with pytest.raises(RollNotUsableError) as excinfo:
            await service.interact(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                object_id=fixture_id,
                action=LIFT_ACTION,
                roll_id=wrong_kind_roll.id,
            )
        assert excinfo.value.code == ErrorCode.ROLL_NOT_USABLE

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused")
            assert len(refused) == 1
            assert refused[0]["args"]["rollId"] == wrong_kind_roll.id
            assert refused[0]["rollIds"] == [wrong_kind_roll.id]

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_refuses_a_roll_already_spent_by_an_earlier_ok_interact(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="interact-already-spent"
        )

        roll_event = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=11,
        )

        first = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=LIFT_ACTION,
            roll_id=roll_event.id,
        )
        assert first is True

        with pytest.raises(RollNotUsableError) as excinfo:
            await service.interact(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                object_id=fixture_id,
                action=CUT_ACTION,
                roll_id=roll_event.id,
            )
        assert excinfo.value.code == ErrorCode.ROLL_NOT_USABLE

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 1  # the second attempt wrote no `ok` row

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_raises_not_found_for_an_object_on_a_foreign_run(playthrough_db):
    async def _scenario():
        _user_a, _run_a, character_a, _fixture_a = await _reach_lair_maw(
            playthrough_db, username="interact-foreign-a"
        )
        _user_b, _run_b, _character_b, fixture_b = await _reach_lair_maw(
            playthrough_db, username="interact-foreign-b"
        )

        with pytest.raises(GameObjectNotFoundError):
            await service.interact(
                playthrough_db,
                user_id=_user_a,
                actor_id=character_a.id,
                object_id=fixture_b,
                action=LIFT_ACTION,
            )

    asyncio.run(_scenario())
