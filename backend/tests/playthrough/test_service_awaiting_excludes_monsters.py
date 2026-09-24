"""Sprint 010/11 round 4, Fault A -- ← finding: a monster's own attack
roll (`roll_dice`/`attack`'s `roll_requested`) dangled with no matching
`roll` after a session race, and `get_awaiting` read that back as
`"roll:<id>"` -- the play screen showed the *player* a "Roll 1d20+4"
button for a monster's own attack, and pressing it (posting `{text:
null}`) fell through to a DM-led filler turn instead of resolving
anything (`game.service.run_turn`'s own guard covers that half; this file
covers `get_awaiting` itself).

Real database throughout (`@pytest.mark.database`): `get_awaiting` reads
the transcript back through the ORM, and a monster's own dangling row is
built directly through the one writer, `append_event`, rather than through
`roll`/`request_player_roll` (which always write a matching pair) -- the
only way to reproduce a row that fell out of sync without also
reproducing the race itself (covered instead, at the `ToolNode` layer, by
`tests/game/test_concurrent_monster_rolls_database.py`).
"""

import asyncio

import pytest
from sqlalchemy import text

from app.core.ids import generate_id
from app.modules.playthrough import service as playthrough_service

CAMPAIGN_ID = "greenhollow"


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _first_goblin_id(session, run_id: str) -> str:
    row = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = 'goblin' LIMIT 1"
            ),
            {"run_id": run_id},
        )
    ).one()
    return row.id


async def _setup(playthrough_db):
    """A run, its own character, and the adventure's goblins already
    placed -- `enter_adventure` alone puts creatures on the board, no walk
    needed, since `get_awaiting`/`append_event` care about the actor's own
    `member_id`, never its position."""
    owner_id = generate_id()
    await _insert_user(playthrough_db, owner_id, username="awaiting-owner")
    await playthrough_db.commit()

    run = await playthrough_service.start_campaign_run(
        playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
    )
    character = await playthrough_service.create_character(
        playthrough_db, user_id=owner_id, run_id=run.id
    )
    await playthrough_service.enter_adventure(playthrough_db, user_id=owner_id, run_id=run.id)
    goblin_id = await _first_goblin_id(playthrough_db, run.id)
    return owner_id, run, character, goblin_id


@pytest.mark.database
def test_a_dangling_monster_roll_request_is_never_awaited(playthrough_db):
    async def scenario():
        owner_id, run, _character, goblin_id = await _setup(playthrough_db)

        # A monster's own attack roll, requested but never answered -- the
        # shape a session race left behind (Fault A). Built directly
        # through `append_event`, the one writer, rather than `roll`
        # (which never leaves a request unanswered on its own).
        await playthrough_service.append_event(
            playthrough_db,
            run_id=run.id,
            type="roll_requested",
            visibility="player",
            payload={"kind": "attack", "actor_id": goblin_id, "formula": "1d20+4", "context": {}},
        )
        await playthrough_db.commit()

        awaiting = await playthrough_service.get_awaiting(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == "none"

    asyncio.run(scenario())


@pytest.mark.database
def test_a_dangling_monster_roll_never_hides_a_real_pending_answer(playthrough_db):
    """A monster's own dangling request must be skipped, not treated as
    the newest thing to report -- a genuinely pending player question
    written after it still surfaces."""

    async def scenario():
        owner_id, run, _character, goblin_id = await _setup(playthrough_db)

        await playthrough_service.append_event(
            playthrough_db,
            run_id=run.id,
            type="roll_requested",
            visibility="player",
            payload={"kind": "attack", "actor_id": goblin_id, "formula": "1d20+4", "context": {}},
        )
        await playthrough_db.commit()

        await playthrough_service.ask_player(
            playthrough_db,
            user_id=owner_id,
            run_id=run.id,
            text="Which door do you take?",
            options=["left", "right"],
        )

        question_id = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'question' ORDER BY id DESC LIMIT 1"
                ),
                {"run_id": run.id},
            )
        ).scalar_one()

        awaiting = await playthrough_service.get_awaiting(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == f"answer:{question_id}"

    asyncio.run(scenario())


@pytest.mark.database
def test_a_player_characters_own_dangling_roll_is_still_awaited(playthrough_db):
    """The exclusion is actor-specific, not blanket: a player character's
    own unanswered roll request still surfaces exactly as before."""

    async def scenario():
        owner_id, run, character, _goblin_id = await _setup(playthrough_db)

        requested = await playthrough_service.request_player_roll(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "wisdom"},
        )

        awaiting = await playthrough_service.get_awaiting(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == f"roll:{requested.id}"

    asyncio.run(scenario())
