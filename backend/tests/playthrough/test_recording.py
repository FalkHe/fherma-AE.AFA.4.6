"""WI3 (sprint 011/03): `record_player_action`, `record_answer`,
`record_narration` and `record_outcome` -- the rules layer's own recording
functions, replacing every `commit`/`append_event` the game module used to
own itself.

Database-backed (`playthrough_db`, `tests/playthrough/conftest.py`), same
setup path as `test_lifecycle_mutations.py`: no `pytest-asyncio`, every
async call in one test wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy import text

from app.core.ids import generate_id
from app.modules.playthrough import service

CAMPAIGN_ID = "greenhollow"


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _run_and_user(db, *, username: str):
    user_id = generate_id()
    await _insert_user(db, user_id, username=username)
    await db.commit()
    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    return user_id, run


@pytest.mark.database
def test_record_player_action_writes_player_action_with_turn(playthrough_db):
    async def _scenario():
        user_id, run = await _run_and_user(playthrough_db, username="record-action")
        turn_id = generate_id()

        event = await service.record_player_action(
            playthrough_db, user_id=user_id, run_id=run.id, text="I look around", turn_id=turn_id
        )

        assert event.type == "player_action"
        assert event.visibility == "player"
        assert event.turn_id == turn_id
        assert event.payload["text"] == "I look around"
        assert event.payload["answersQuestionId"] is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_record_answer_writes_player_action_with_question_id(playthrough_db):
    async def _scenario():
        user_id, run = await _run_and_user(playthrough_db, username="record-answer")
        turn_id = generate_id()
        question_id = generate_id()

        event = await service.record_answer(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            text="the left door",
            question_id=question_id,
            turn_id=turn_id,
        )

        assert event.type == "player_action"
        assert event.turn_id == turn_id
        assert event.payload["text"] == "the left door"
        assert event.payload["answersQuestionId"] == question_id

    asyncio.run(_scenario())


@pytest.mark.database
def test_record_narration_writes_narration_with_turn_and_usage(playthrough_db):
    async def _scenario():
        user_id, run = await _run_and_user(playthrough_db, username="record-narration")
        turn_id = generate_id()

        event = await service.record_narration(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            text="The door creaks open.",
            turn_id=turn_id,
        )

        assert event.type == "narration"
        assert event.visibility == "player"
        assert event.turn_id == turn_id
        assert event.payload["text"] == "The door creaks open."

    asyncio.run(_scenario())


@pytest.mark.database
def test_record_narration_activates_a_ready_run(playthrough_db):
    async def _scenario():
        user_id, run = await _run_and_user(playthrough_db, username="record-activate")
        await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        await playthrough_db.refresh(run)
        assert run.status == "ready"

        await service.record_narration(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            text="Opening scene.",
            turn_id=generate_id(),
        )

        refreshed = await service.get_campaign_run(playthrough_db, user_id=user_id, run_id=run.id)
        assert refreshed.status == "active"

    asyncio.run(_scenario())


@pytest.mark.database
def test_record_outcome_writes_ok_tool_call(playthrough_db):
    async def _scenario():
        user_id, run = await _run_and_user(playthrough_db, username="record-outcome-ok")
        turn_id = generate_id()

        event = await service.record_outcome(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            name="lookup_rule",
            args={"topic": "grappling"},
            outcome={"matched": True},
            turn_id=turn_id,
            roll_ids=["r1"],
        )

        assert event.type == "tool_call"
        assert event.visibility == "dm"
        assert event.turn_id == turn_id
        assert event.payload["name"] == "lookup_rule"
        assert event.payload["args"] == {"topic": "grappling"}
        assert event.payload["rollIds"] == ["r1"]
        assert event.payload["result"] == "ok"
        assert event.payload["outcome"] == {"matched": True}

    asyncio.run(_scenario())


@pytest.mark.database
def test_record_outcome_writes_refused_tool_call(playthrough_db):
    async def _scenario():
        user_id, run = await _run_and_user(playthrough_db, username="record-outcome-refused")

        event = await service.record_outcome(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            name="set_hostility",
            args={"actorId": "x"},
            outcome={"reason": "actor is not a creature"},
            turn_id=None,
        )

        assert event.payload["result"] == "refused"

    asyncio.run(_scenario())
