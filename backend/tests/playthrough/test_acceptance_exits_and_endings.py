"""qa acceptance tests -- sprint 005/06b "an exit moves the party, ends the
adventure, or finishes the game"
(`docs/intents/005-game-state-services/sprints/06b-exits-and-endings/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`
or `.errors` themselves -- those are this sprint's own work items, written
in parallel, and this file never imports or reads them.

`use_exit` has no route by design (plan.md: "phase 8's tool layer is its
only caller"), so every criterion here drives the service directly against
a real database -- both tests carry `@pytest.mark.database`.

The database half plays the shipped `greenhollow/v1` content exactly as
authored (`backend/content/campaigns/greenhollow/v1/adventures/
goblins-of-greenhollow.json`): `village-green` --`to-thornway`--> `thornway`
--`to-lair-maw`--> `lair-maw` --`to-lair-hollow`--> `lair-hollow`
--`leave-the-hollow` (`adventure_end`)--> the adventure completes, and,
Greenhollow being the campaign's only (hence last) adventure, so does the
campaign run. Every scene along that path is already populated by
`enter_adventure` (mira and a horseshoe on the green, goblins and a
thornbrush screen in the maw, the goblin boss, a rank-and-file goblin and a
wool sack in the hollow) -- AC3 reads every one of those positions back
after the ending exit, not just the actor's own.

The refusal half of AC2 is read back from a **second** connection to the
same scratch database, opened after the refused `use_exit` call has
already raised -- never from the session `use_exit` itself ran on. A
flushed-but-uncommitted row is visible to the session that wrote it
regardless of whether the service ever committed, so that session can
never tell a genuinely persisted refusal apart from one that would vanish
under the caller's rollback; only an independent connection can. Same
pattern as `test_acceptance_cost_and_live_signal.py`'s own `writer_engine`,
in reverse (there a second connection writes while the test's own session
reads; here a second connection reads while the test's own session wrote).

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
in a test is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service
or errors module themselves -- this suite is red until `use_exit` lands,
and green once it does.
"""

import asyncio
import json
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.playthrough import service as playthrough_service

CAMPAIGN_ID = "greenhollow"
ADVENTURE_ID = "goblins-of-greenhollow"

ENTRY_SCENE = "village-green"
TO_THORNWAY = "to-thornway"  # village-green -> thornway
THORNWAY_SCENE = "thornway"
TO_LAIR_MAW = "to-lair-maw"  # thornway -> lair-maw
LAIR_MAW_SCENE = "lair-maw"
TO_LAIR_HOLLOW = "to-lair-hollow"  # lair-maw -> lair-hollow
LAIR_HOLLOW_SCENE = "lair-hollow"
LEAVE_THE_HOLLOW = "leave-the-hollow"  # lair-hollow -> adventure_end


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _actor_position(session, actor_id: str):
    return (
        await session.execute(
            text("SELECT adventure_run_id, scene_id FROM objects WHERE id = :id"),
            {"id": actor_id},
        )
    ).one()


class _second_connection:
    """An `AsyncSession` on its own connection to the same scratch
    database `playthrough_db` already pinned `DATABASE_URL` to -- never the
    session under test. The only way to read what is genuinely committed
    rather than merely flushed and still pending in the other session's
    open transaction."""

    async def __aenter__(self):
        self._engine = create_async_engine(os.environ["DATABASE_URL"])
        sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._session = sessionmaker()
        return self._session

    async def __aexit__(self, *exc_info) -> None:
        await self._session.close()
        await self._engine.dispose()


def _payload(row) -> dict:
    payload = row.payload
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload


async def _dm_tool_call_events(session, run_id: str):
    rows = (
        await session.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' AND visibility = 'dm' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [_payload(row) for row in rows]


@pytest.mark.database
def test_ac2_an_ordinary_exit_moves_the_actor_or_is_refused_and_recorded(playthrough_db):
    # <- AC2
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac2-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        adventure_run = await playthrough_service.enter_adventure(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert adventure_run.adventure_id == ADVENTURE_ID

        before_position = await _actor_position(playthrough_db, character.id)
        assert before_position.adventure_run_id == adventure_run.id
        assert before_position.scene_id == ENTRY_SCENE

        # -- Using an ordinary exit on the actor's current scene moves the
        # actor to the scene it leads to, and leaves which adventure they
        # are in unchanged.
        result = await playthrough_service.use_exit(
            playthrough_db, user_id=owner_id, actor_id=character.id, exit_id=TO_THORNWAY
        )
        assert result is None

        after_move = await _actor_position(playthrough_db, character.id)
        assert after_move.scene_id == THORNWAY_SCENE
        assert after_move.adventure_run_id == adventure_run.id  # unchanged

        # It is recorded in the transcript, visible to the player. Sprint
        # 010/04 also has `enter_adventure` itself append one `scene_entered`
        # for the opening scene (`village-green`), so this walk's own move
        # is the *second* one, not the only one.
        player_events = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        scene_entered = [e for e in player_events if e.type == "scene_entered"]
        assert len(scene_entered) == 2
        entered_payload = _payload(scene_entered[-1])
        assert entered_payload.get("adventureRunId") == str(adventure_run.id)
        assert entered_payload.get("sceneId") == THORNWAY_SCENE

        # A successful use also records a `tool_call` at `dm` visibility
        # with `result: "ok"`.
        dm_calls = await _dm_tool_call_events(playthrough_db, run.id)
        ok_calls = [p for p in dm_calls if p.get("result") == "ok"]
        assert len(ok_calls) == 1
        assert ok_calls[0].get("name") == "use_exit"
        assert ok_calls[0].get("args", {}).get("actorId") == str(character.id)
        assert ok_calls[0].get("args", {}).get("exitId") == TO_THORNWAY

        # -- Using an exit that is not on the actor's current scene (the
        # actor now stands on `thornway`; `to-thornway` belongs to
        # `village-green`, not `thornway`) is refused, and nothing about
        # the world changes.
        players_events_before_refusal = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        with pytest.raises(Exception) as exc_info:
            await playthrough_service.use_exit(
                playthrough_db, user_id=owner_id, actor_id=character.id, exit_id=TO_THORNWAY
            )
        assert exc_info.value.code == ErrorCode.EXIT_NOT_AVAILABLE

        # Everything below is read from a **second** connection -- never
        # `playthrough_db`, the session `use_exit` just raised on. A row
        # `append_event` only flushed (never committed) is still visible to
        # the session that flushed it; only an independent connection can
        # tell that apart from a row genuinely committed to the database,
        # which is the entire point of the refusal recording its own commit
        # before raising.
        async with _second_connection() as reader:
            after_refusal = await _actor_position(reader, character.id)
            assert after_refusal.scene_id == after_move.scene_id
            assert after_refusal.adventure_run_id == after_move.adventure_run_id

            # The player's own read of the transcript shows nothing at all
            # for the refusal -- same events, in the same order, as before
            # it.
            players_events_after_refusal = await playthrough_service.list_events(
                reader, user_id=owner_id, run_id=run.id
            )
            assert [e.id for e in players_events_after_refusal] == [
                e.id for e in players_events_before_refusal
            ]

            # The refusal is itself recorded -- exactly one `tool_call`
            # entry at `dm` visibility, marked `refused`, naming the
            # mechanism, the actor and the exit asked for -- and it
            # genuinely persisted: reachable from a connection that never
            # saw the attempt that wrote it, not merely flushed into the
            # writer's own still-open transaction.
            dm_calls_after = await _dm_tool_call_events(reader, run.id)
            refused_calls = [p for p in dm_calls_after if p.get("result") == "refused"]
            assert len(refused_calls) == 1
            assert refused_calls[0].get("name") == "use_exit"
            assert refused_calls[0].get("args", {}).get("actorId") == str(character.id)
            assert refused_calls[0].get("args", {}).get("exitId") == TO_THORNWAY

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_the_ending_exit_completes_the_adventure_and_finishes_the_game(playthrough_db):
    # <- AC3
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac3-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        adventure_run = await playthrough_service.enter_adventure(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        # Walk the actor to the far end of the adventure, through two more
        # ordinary exits, before touching the ending one.
        await playthrough_service.use_exit(
            playthrough_db, user_id=owner_id, actor_id=character.id, exit_id=TO_THORNWAY
        )
        await playthrough_service.use_exit(
            playthrough_db, user_id=owner_id, actor_id=character.id, exit_id=TO_LAIR_MAW
        )
        await playthrough_service.use_exit(
            playthrough_db, user_id=owner_id, actor_id=character.id, exit_id=TO_LAIR_HOLLOW
        )

        position_before_ending = await _actor_position(playthrough_db, character.id)
        assert position_before_ending.scene_id == LAIR_HOLLOW_SCENE

        # Every positioned object in the run -- the actor and the whole
        # cast the content places along the way (mira, the goblins, the
        # goblin boss, the wool sack) -- snapshotted just before the
        # ending exit is used.
        positions_before = {
            row.id: (row.adventure_run_id, row.scene_id)
            for row in (
                await playthrough_db.execute(
                    text(
                        "SELECT id, adventure_run_id, scene_id FROM objects "
                        "WHERE campaign_run_id = :run_id AND adventure_run_id IS NOT NULL"
                    ),
                    {"run_id": run.id},
                )
            ).all()
        }
        assert len(positions_before) > 1  # the actor plus at least the seeded cast

        result = await playthrough_service.use_exit(
            playthrough_db, user_id=owner_id, actor_id=character.id, exit_id=LEAVE_THE_HOLLOW
        )
        assert result is None

        # The adventure run completed: its status and the time it
        # finished.
        adventure_row = (
            await playthrough_db.execute(
                text("SELECT status, completed_at FROM adventure_runs WHERE id = :id"),
                {"id": adventure_run.id},
            )
        ).one()
        assert adventure_row.status == "completed"
        assert adventure_row.completed_at is not None

        # Recorded, visible to the player.
        player_events = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        completed_events = [e for e in player_events if e.type == "adventure_completed"]
        assert len(completed_events) == 1
        completed_payload = _payload(completed_events[0])
        assert completed_payload.get("adventureRunId") == str(adventure_run.id)

        # Greenhollow's is the campaign's only, and therefore last,
        # adventure -- the game itself becomes finished.
        campaign_status = (
            await playthrough_db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": run.id}
            )
        ).scalar_one()
        assert campaign_status == "finished"

        # Every positioned object -- including the actor itself -- keeps
        # exactly the position it held before the ending exit was used:
        # nobody is cleared away when an adventure ends.
        positions_after = {
            row.id: (row.adventure_run_id, row.scene_id)
            for row in (
                await playthrough_db.execute(
                    text(
                        "SELECT id, adventure_run_id, scene_id FROM objects "
                        "WHERE campaign_run_id = :run_id AND adventure_run_id IS NOT NULL"
                    ),
                    {"run_id": run.id},
                )
            ).all()
        }
        assert positions_after == positions_before

    asyncio.run(_scenario())
