"""WI2 (sprint 011/03): `set_hostility`, `leave_scene`, `enter_next_adventure`
and `finish_run` -- durable world changes outside fixture/exit/item mechanics.

Database-backed throughout (`playthrough_db`, `tests/playthrough/conftest.py`)
against the shipped `greenhollow/v1` content, the same path
`test_authored_checks.py`'s database tests walk: `start_campaign_run` ->
`create_character` -> `enter_adventure` gives one real, positioned creature
to act on. No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every
async call in one test is wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy import select, text

from app.core.ids import generate_id
from app.modules.playthrough import service
from app.modules.playthrough.models import GameObject

CAMPAIGN_ID = "greenhollow"


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _positioned_character(db, *, username: str):
    user_id = generate_id()
    await _insert_user(db, user_id, username=username)
    await db.commit()
    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id)
    await service.enter_adventure(db, user_id=user_id, run_id=run.id)
    await db.refresh(character)
    return user_id, run, character


@pytest.mark.database
def test_set_hostility_flag_is_set_and_read_back(playthrough_db):
    async def _scenario():
        user_id, _run, character = await _positioned_character(
            playthrough_db, username="hostility-set"
        )

        result = await service.set_hostility(
            playthrough_db, user_id=user_id, actor_id=character.id, hostile=True
        )
        assert result.status == "ok"
        assert result.facts == {"hostile": True}
        assert result.event_ids

        await playthrough_db.refresh(character)
        assert character.state["hostile"] is True

    asyncio.run(_scenario())


@pytest.mark.database
def test_set_hostility_refuses_a_non_creature_actor(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="hostility-item")
        await playthrough_db.commit()
        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)
        await playthrough_db.refresh(character)

        items = await playthrough_db.execute(
            select(GameObject.id).where(
                GameObject.campaign_run_id == run.id, GameObject.kind == "item"
            )
        )
        item_id = items.scalars().first()
        assert item_id is not None

        result = await service.set_hostility(
            playthrough_db, user_id=user_id, actor_id=item_id, hostile=True
        )
        assert result.status == "refused"
        assert result.reason is not None

    asyncio.run(_scenario())


@pytest.mark.database
def test_leave_scene_clears_position_and_remembers_where(playthrough_db):
    async def _scenario():
        user_id, _run, character = await _positioned_character(
            playthrough_db, username="leave-scene"
        )
        left_scene_id = character.scene_id
        left_adventure_run_id = character.adventure_run_id

        result = await service.leave_scene(playthrough_db, user_id=user_id, actor_id=character.id)
        assert result.status == "ok"

        await playthrough_db.refresh(character)
        assert character.scene_id is None
        assert character.adventure_run_id is None
        assert character.state["left_scene"] == {
            "sceneId": left_scene_id,
            "adventureRunId": left_adventure_run_id,
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_leave_scene_refuses_an_actor_already_gone(playthrough_db):
    async def _scenario():
        user_id, _run, character = await _positioned_character(
            playthrough_db, username="leave-twice"
        )
        first = await service.leave_scene(playthrough_db, user_id=user_id, actor_id=character.id)
        assert first.status == "ok"

        second = await service.leave_scene(playthrough_db, user_id=user_id, actor_id=character.id)
        assert second.status == "refused"
        assert second.reason is not None

    asyncio.run(_scenario())


@pytest.mark.database
def test_finish_run_marks_the_run_finished_with_its_outcome(playthrough_db):
    async def _scenario():
        user_id, run, _character = await _positioned_character(
            playthrough_db, username="finish-run"
        )

        result = await service.finish_run(
            playthrough_db, user_id=user_id, run_id=run.id, outcome="victory"
        )
        assert result.status == "ok"
        assert result.facts == {"outcome": "victory"}

        await playthrough_db.refresh(run)
        assert run.status == "finished"

        rows = await playthrough_db.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'system' ORDER BY created_at DESC LIMIT 1"
            ),
            {"run_id": run.id},
        )
        payload = rows.scalar_one()
        assert payload["details"]["outcome"] == "victory"

    asyncio.run(_scenario())


@pytest.mark.database
def test_finish_run_refuses_a_second_finish(playthrough_db):
    async def _scenario():
        user_id, run, _character = await _positioned_character(
            playthrough_db, username="finish-twice"
        )

        first = await service.finish_run(
            playthrough_db, user_id=user_id, run_id=run.id, outcome="defeat"
        )
        assert first.status == "ok"

        second = await service.finish_run(
            playthrough_db, user_id=user_id, run_id=run.id, outcome="defeat"
        )
        assert second.status == "refused"
        assert second.reason is not None

    asyncio.run(_scenario())
