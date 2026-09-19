"""WI1 (sprint 06b): using an exit -- AC2, AC3.

Gates (an unknown/foreign actor, an archived run, an invalid status) are
engine-free, `FakeSession` stands in for `AsyncSession` exactly the way
`test_service_enter_adventure.py` does it for `enter_adventure`. Everything
that needs a real move, a real ending, or the refusal's own record is
`@pytest.mark.database`, driven against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content, the same
path qa's own `test_acceptance_exits_and_endings.py` walks.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
is wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.playthrough import service
from app.modules.playthrough.errors import (
    CampaignRunNotFoundError,
    ExitNotAvailableError,
    GameObjectNotFoundError,
    InvalidRunStatusError,
    RunArchivedError,
)
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, GameObject

CAMPAIGN_ID = "greenhollow"
ADVENTURE_ID = "goblins-of-greenhollow"
ENTRY_SCENE = "village-green"
TO_THORNWAY = "to-thornway"


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


# --- FakeSession, tailored to use_exit's own query shape ----------------


class FakeResult:
    def __init__(self, *, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    """Engine-free stand-in for `AsyncSession`, only as deep as the gate
    tests below need: a queue of `select` results, and enough bookkeeping
    to prove a gate failure never reaches `add`/`commit`."""

    def __init__(self, *results):
        self._results = list(results)
        self.added: list[object] = []
        self.committed = 0
        self.rolled_back = 0

    async def execute(self, stmt):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        self.rolled_back += 1


def _object(object_id="actor-1", *, campaign_run_id="run-1", scene_id=None, adventure_run_id=None):
    return GameObject(
        id=object_id,
        campaign_run_id=campaign_run_id,
        kind="creature",
        instance_key="pc:member-1:1",
        name="Fixture Actor",
        scene_id=scene_id,
        adventure_run_id=adventure_run_id,
    )


def _member(run_id="run-1", user_id="user-1"):
    return CampaignRunMember(campaign_run_id=run_id, user_id=user_id, role="owner")


def _run(run_id="run-1", *, status="ready", campaign_id=CAMPAIGN_ID):
    return CampaignRun(id=run_id, campaign_id=campaign_id, content_version="v1", status=status)


# --- gates ----------------------------------------------------------------


def test_use_exit_raises_game_object_not_found_for_an_unknown_actor():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(GameObjectNotFoundError):
        asyncio.run(
            service.use_exit(db, user_id="user-1", actor_id="no-such-actor", exit_id="an-exit")
        )

    assert db.added == []
    assert db.committed == 0


def test_use_exit_raises_not_found_for_an_actor_on_a_foreign_run():
    # <- the actor exists, but the caller is not a member of its run: this
    # answers identically to an unknown actor (no branch tells them apart).
    db = FakeSession(FakeResult(scalar=_object()), FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(service.use_exit(db, user_id="user-1", actor_id="actor-1", exit_id="an-exit"))

    assert db.added == []
    assert db.committed == 0


def test_use_exit_raises_run_archived_for_an_archived_run():
    db = FakeSession(
        FakeResult(scalar=_object()),
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run(status="archived")),
    )

    with pytest.raises(RunArchivedError):
        asyncio.run(service.use_exit(db, user_id="user-1", actor_id="actor-1", exit_id="an-exit"))

    assert db.committed == 0


@pytest.mark.parametrize("status", ["setup", "finished"])
def test_use_exit_raises_invalid_run_status_outside_ready_or_active(status):
    db = FakeSession(
        FakeResult(scalar=_object()),
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run(status=status)),
    )

    with pytest.raises(InvalidRunStatusError):
        asyncio.run(service.use_exit(db, user_id="user-1", actor_id="actor-1", exit_id="an-exit"))

    assert db.committed == 0


# --- the real thing: move, end, finish, refuse ---------------------------


@pytest.mark.database
def test_use_exit_moves_the_actor_and_records_scene_entered_and_a_dm_tool_call(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="use-exit-move")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        adventure_run = await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)

        result = await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id=TO_THORNWAY
        )
        assert result is None

        row = (
            await playthrough_db.execute(
                text("SELECT adventure_run_id, scene_id FROM objects WHERE id = :id"),
                {"id": character.id},
            )
        ).one()
        assert row.scene_id == "thornway"
        assert row.adventure_run_id == adventure_run.id  # unchanged

        events = (
            await playthrough_db.execute(
                text(
                    "SELECT type, visibility, payload FROM events "
                    "WHERE campaign_run_id = :run_id ORDER BY id"
                ),
                {"run_id": run.id},
            )
        ).all()
        scene_entered = [e for e in events if e.type == "scene_entered"]
        assert len(scene_entered) == 1
        assert scene_entered[0].visibility == "player"
        assert scene_entered[0].payload == {
            "adventureRunId": adventure_run.id,
            "sceneId": "thornway",
        }

        ok_calls = [e for e in events if e.type == "tool_call" and e.payload["result"] == "ok"]
        assert len(ok_calls) == 1
        assert ok_calls[0].visibility == "dm"
        assert ok_calls[0].payload["name"] == "use_exit"
        assert ok_calls[0].payload["args"] == {"actorId": character.id, "exitId": TO_THORNWAY}
        assert ok_calls[0].payload["rollIds"] == []

    asyncio.run(_scenario())


@pytest.mark.database
def test_use_exit_commits_exactly_once_on_the_happy_path(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="use-exit-commit")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)

        # A committed row for every step already run proves each call ended
        # in exactly one commit: a fresh connection reads it back.
        await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id=TO_THORNWAY
        )

        count = (
            await playthrough_db.execute(
                text(
                    "SELECT count(*) FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'scene_entered'"
                ),
                {"run_id": run.id},
            )
        ).scalar_one()
        assert count == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_use_exit_ends_the_adventure_and_finishes_the_game_without_touching_positions(
    playthrough_db,
):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="use-exit-end")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        adventure_run = await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)

        for exit_id in ("to-thornway", "to-lair-maw", "to-lair-hollow"):
            await service.use_exit(
                playthrough_db, user_id=user_id, actor_id=character.id, exit_id=exit_id
            )

        positions_before = (
            await playthrough_db.execute(
                text(
                    "SELECT id, adventure_run_id, scene_id FROM objects "
                    "WHERE campaign_run_id = :run_id AND adventure_run_id IS NOT NULL"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(positions_before) > 1  # the actor plus the seeded cast

        result = await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id="leave-the-hollow"
        )
        assert result is None

        adventure_row = (
            await playthrough_db.execute(
                text("SELECT status, completed_at FROM adventure_runs WHERE id = :id"),
                {"id": adventure_run.id},
            )
        ).one()
        assert adventure_row.status == "completed"
        assert adventure_row.completed_at is not None

        campaign_status = (
            await playthrough_db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": run.id}
            )
        ).scalar_one()
        assert campaign_status == "finished"  # greenhollow's only, hence last, adventure

        positions_after = (
            await playthrough_db.execute(
                text(
                    "SELECT id, adventure_run_id, scene_id FROM objects "
                    "WHERE campaign_run_id = :run_id AND adventure_run_id IS NOT NULL"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert {(r.id, r.adventure_run_id, r.scene_id) for r in positions_after} == {
            (r.id, r.adventure_run_id, r.scene_id) for r in positions_before
        }

        events = (
            await playthrough_db.execute(
                text(
                    "SELECT type, visibility, payload FROM events "
                    "WHERE campaign_run_id = :run_id AND type = 'adventure_completed'"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(events) == 1
        assert events[0].visibility == "player"
        assert events[0].payload == {"adventureRunId": adventure_run.id}

    asyncio.run(_scenario())


@pytest.mark.database
def test_use_exit_refuses_an_exit_not_on_the_actors_scene_and_records_it_before_raising(
    playthrough_db,
):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="use-exit-refuse")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)

        before = (
            await playthrough_db.execute(
                text("SELECT adventure_run_id, scene_id FROM objects WHERE id = :id"),
                {"id": character.id},
            )
        ).one()

        with pytest.raises(ExitNotAvailableError) as excinfo:
            await service.use_exit(
                playthrough_db, user_id=user_id, actor_id=character.id, exit_id="leave-the-hollow"
            )
        assert excinfo.value.code == ErrorCode.EXIT_NOT_AVAILABLE

        # Nothing about the world changed.
        after = (
            await playthrough_db.execute(
                text("SELECT adventure_run_id, scene_id FROM objects WHERE id = :id"),
                {"id": character.id},
            )
        ).one()
        assert after == before

        # The refusal survived the raise: read back here with no rollback
        # or extra commit of our own in between.
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
        assert refused[0].payload["result"] == "refused"
        assert refused[0].payload["name"] == "use_exit"
        assert refused[0].payload["args"] == {
            "actorId": character.id,
            "exitId": "leave-the-hollow",
        }
        assert "reason" in refused[0].payload["outcome"]

        # The player's own transcript shows nothing for it.
        player_events = await service.list_events(playthrough_db, user_id=user_id, run_id=run.id)
        assert all(e.type != "tool_call" for e in player_events)

    asyncio.run(_scenario())


@pytest.mark.database
def test_use_exit_refuses_an_actor_with_no_current_scene_the_same_way(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="use-exit-no-scene")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        # No `enter_adventure` call: the character exists but has never
        # been positioned anywhere -- `scene_id` is `None`.
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)

        with pytest.raises(ExitNotAvailableError) as excinfo:
            await service.use_exit(
                playthrough_db, user_id=user_id, actor_id=character.id, exit_id=TO_THORNWAY
            )
        assert excinfo.value.code == ErrorCode.EXIT_NOT_AVAILABLE

        refused = (
            await playthrough_db.execute(
                text(
                    "SELECT visibility, payload FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call'"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(refused) == 1
        assert refused[0].payload["result"] == "refused"

    asyncio.run(_scenario())


@pytest.mark.database
def test_use_exit_refusal_leaves_the_callers_own_loaded_objects_readable(playthrough_db):
    """The warning carried over from 06a: whatever `use_exit` does on its
    refusal path must not call a session-wide `db.rollback()` -- that would
    expire every ORM object the caller already holds, including `run`,
    loaded here before the refused call. `use_exit` only ever commits on
    this path, and the session is built with `expire_on_commit=False`
    (`core/db.py`), so `run` must stay readable with no further round
    trip."""

    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="use-exit-readable")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)

        with pytest.raises(ExitNotAvailableError):
            await service.use_exit(
                playthrough_db, user_id=user_id, actor_id=character.id, exit_id="leave-the-hollow"
            )

        # <- the regression this pins: no `MissingGreenlet` on an ordinary,
        # already-loaded attribute right after the refusal.
        assert run.status == "ready"
        assert run.campaign_id == CAMPAIGN_ID

    asyncio.run(_scenario())
