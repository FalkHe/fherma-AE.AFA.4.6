"""WI2 (sprint 08a): one action per creature per turn, shared by every
acting mechanic -- AC3 (`docs/modules/playthrough.md` §17).

`interact` is the only action-spending mechanic that exists yet (`take`,
`give` and `use_item` land in 08b; `attack` in sprint 09), so it is the
one this suite drives the rule through -- the private helper itself is
never imported or called directly, only observed through `interact`'s own
gate order (WI1's own docstring: the one-action check sits after
`_resolve_actor_and_run`, before the mechanic's own checks).

`drop` does not exist as a mechanic yet, so its "free" status (product
owner's ruling, brief `## Decisions`, superseding the brief's own
assumption) is proven the only way available: a synthetic `drop`
`tool_call` `ok` event is appended directly through `append_event` --
the module's own, only writer of `events` (`AGENTS.md`) -- and a
following `interact` in the same turn must still succeed. If `drop` were
folded into the action set by mistake, that test would start failing.

`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content, walking
the same path `test_service_interact.py` and qa's acceptance suite do:
`village-green` -> `thornway` -> `lair-maw`, where `thorn-screen` stands.

No `pytest-asyncio` (`AGENTS.md` gotchas): every async call in one
scenario is wrapped in one `asyncio.run(...)`.
"""

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service
from app.modules.playthrough.errors import ActionNotAvailableError, AlreadyActedError

CAMPAIGN_ID = "greenhollow"

# `thorn-screen`'s two authored checks (same literals `test_service_
# interact.py` already pins against the shipped content): one needs a
# roll (no `bypassed_by` at all), the other passes with no roll at all
# for the seed character's own knife -- the simplest way to get a second
# "ok" `interact` in a fresh turn without scripting a roll.
LIFT_ACTION = (
    "Lift the lashed brush aside a branch at a time, without letting it scrape on the stone"
)
CUT_ACTION = "Cut through the lashings that hold the screen together"


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _ScriptedRandom:
    """Same seam `test_service_interact.py` and the 07a/07b suites use: a
    fixed, pre-scripted sequence of face values, one per call."""

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
    still-open transaction (same helper `test_service_interact.py`,
    `test_acceptance_exits_and_endings.py` and `test_acceptance_rolls_
    spent_once.py` each keep their own copy of)."""

    async def __aenter__(self):
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
    scene, exactly `test_service_interact.py`'s own path."""
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


async def _tool_calls(db, run_id: str, *, result: str, name: str | None = None) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' AND visibility = 'dm' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [
        row.payload
        for row in rows
        if row.payload["result"] == result and (name is None or row.payload["name"] == name)
    ]


@pytest.mark.database
def test_second_action_in_the_same_turn_is_refused_with_already_acted(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="one-action-second-refused"
        )
        turn_id = generate_id()

        first = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=CUT_ACTION,
            turn_id=turn_id,
        )
        assert first is True

        with pytest.raises(AlreadyActedError) as excinfo:
            await service.interact(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                object_id=fixture_id,
                action=LIFT_ACTION,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.ALREADY_ACTED

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="interact")
            assert len(refused) == 1
            assert refused[0]["args"] == {
                "actorId": character.id,
                "objectId": fixture_id,
                "action": LIFT_ACTION,
            }

        # The one committed real action is the only `ok` `tool_call`
        # for this creature in this turn -- the second attempt never
        # reached the mechanic's own checks at all.
        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="interact")
        assert len(ok_calls) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_new_turn_allows_the_same_creature_to_act_again(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="one-action-new-turn"
        )
        turn_a = generate_id()
        first = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=CUT_ACTION,
            turn_id=turn_a,
        )
        assert first is True

        turn_b = generate_id()
        second = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=CUT_ACTION,
            turn_id=turn_b,
        )
        assert second is True

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="interact")
        assert len(ok_calls) == 2

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_refused_attempt_does_not_spend_the_turn(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="one-action-refusal-free"
        )
        turn_id = generate_id()

        with pytest.raises(ActionNotAvailableError):
            await service.interact(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                object_id=fixture_id,
                action="an action the fixture's author never wrote",
                turn_id=turn_id,
            )

        # The real action right after, in the very same turn, still
        # succeeds -- the refusal above spent nothing.
        success = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=CUT_ACTION,
            turn_id=turn_id,
        )
        assert success is True

    asyncio.run(_scenario())


@pytest.mark.database
def test_using_an_exit_and_rolling_do_not_spend_the_turn(playthrough_db):
    async def _scenario():
        # `use_exit` takes no `turn_id` of its own -- it always lands in
        # the untagged turn -- so the real action below must land there
        # too (no `turn_id` given) to actually share a bucket with them.
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="one-action-free-moves")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)

        await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id="to-thornway"
        )
        await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id="to-lair-maw"
        )
        await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=1,
        )

        fixture_id = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                    "AND template_id = 'thorn-screen'"
                ),
                {"run_id": run.id},
            )
        ).scalar_one()

        # Two `use_exit` calls and one roll already sit in this very
        # (untagged) turn; were either counted as an action, this would
        # raise `AlreadyActedError` instead of succeeding.
        success = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=CUT_ACTION,
        )
        assert success is True

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_drop_tool_call_does_not_spend_the_turn(playthrough_db):
    """`drop` is not a mechanic yet (08b), so its "free" status is proven
    by appending a synthetic `tool_call` naming it directly through
    `append_event` -- if `drop` were ever folded into the action set by
    mistake, this is the test that would catch it (product owner's
    ruling, brief `## Decisions`)."""

    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="one-action-drop-free"
        )
        turn_id = generate_id()

        await service.append_event(
            playthrough_db,
            run_id=run.id,
            type="tool_call",
            visibility="dm",
            turn_id=turn_id,
            payload={
                "name": "drop",
                "args": {"actorId": character.id, "itemId": "some-item"},
                "roll_ids": [],
                "result": "ok",
                "outcome": {},
            },
        )
        await playthrough_db.commit()

        success = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=CUT_ACTION,
            turn_id=turn_id,
        )
        assert success is True

    asyncio.run(_scenario())
