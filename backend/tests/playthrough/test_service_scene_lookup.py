"""Sprint 010/10, ← finding: a scene with several identically-named
monsters gave the model no way to tell them apart, and no actionable way
back when it named the wrong one (or one with no attacks at all).

`resolve_actor_ref` -- an `actor_id` argument resolved to one creature, by
id or by a living creature's own name -- and `describe_scene_creatures` --
the scene's own creatures, id first, role, HP and attack names -- are the
two building blocks; `request_player_roll`'s three new guards (player-only
actor, player-only kind, a `custom` roll must be real dice) live here too,
alongside the existing gate tests in `test_service_rolls.py`.

Gates are engine-free (`FakeSession`, `test_service_rolls.py`'s own
shape); the real lair-maw scene (three identical `goblin`s, per
`greenhollow/v1`) is `@pytest.mark.database`.

No `pytest-asyncio` (AGENTS.md gotchas): every async call in one scenario
is wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.modules.playthrough import service
from app.modules.playthrough.errors import GameObjectNotFoundError
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, GameObject

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"


# --- gates, engine-free (FakeSession, `test_service_rolls.py`'s shape) ----


class FakeResult:
    def __init__(self, *, scalar=None, scalars_list=None):
        self._scalar = scalar
        self._scalars_list = scalars_list or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars_list


class FakeSession:
    def __init__(self, *results):
        self._results = list(results)
        self.committed = 0

    async def execute(self, stmt):
        return self._results.pop(0)

    async def commit(self):
        self.committed += 1


def _goblin(object_id="gob-1", *, name="Goblin Raider", is_alive=True):
    return GameObject(
        id=object_id,
        campaign_run_id="run-1",
        kind="creature",
        template_id="goblin",
        instance_key=f"{object_id}:1",
        name=name,
        scene_id="lair-maw",
        current_hp=7,
        max_hp=7,
        armour_class=13,
        is_alive=is_alive,
        state={},
    )


def test_resolve_actor_ref_matches_a_real_id_outright():
    goblin = _goblin()
    db = FakeSession(FakeResult(scalar=goblin))

    resolved = asyncio.run(service.resolve_actor_ref(db, run_id="run-1", ref="gob-1"))

    assert resolved is goblin


def test_resolve_actor_ref_falls_back_to_a_living_creatures_own_name():
    # No id "Goblin Raider" exists -- the id lookup misses, so the second
    # query (every living creature of the run) is where the name match
    # happens.
    goblin = _goblin()
    db = FakeSession(FakeResult(scalar=None), FakeResult(scalars_list=[goblin]))

    resolved = asyncio.run(service.resolve_actor_ref(db, run_id="run-1", ref="goblin raider"))

    assert resolved is goblin


def test_resolve_actor_ref_names_the_ref_when_neither_matches():
    db = FakeSession(FakeResult(scalar=None), FakeResult(scalars_list=[]))

    with pytest.raises(GameObjectNotFoundError) as exc_info:
        asyncio.run(service.resolve_actor_ref(db, run_id="run-1", ref="Bugbear"))
    assert exc_info.value.object_id == "Bugbear"


def test_describe_scene_creatures_answers_empty_with_no_scene_to_look_at():
    db = FakeSession()

    described = asyncio.run(service.describe_scene_creatures(db, run_id="run-1"))

    assert described == []


def _member(run_id="run-1", user_id="user-1"):
    return CampaignRunMember(campaign_run_id=run_id, user_id=user_id, role="owner")


def _run(run_id="run-1", *, status="active"):
    return CampaignRun(id=run_id, campaign_id=CAMPAIGN_ID, content_version=VERSION, status=status)


def test_request_player_roll_refuses_an_actor_that_is_not_a_player_character():
    # A monster's own turn: `member_id` is unset, exactly a scene creature.
    monster = _goblin()
    db = FakeSession(
        FakeResult(scalar=monster), FakeResult(scalar=_member()), FakeResult(scalar=_run())
    )

    with pytest.raises(ValueError, match="player character"):
        asyncio.run(
            service.request_player_roll(
                db,
                user_id="user-1",
                actor_id="gob-1",
                kind="saving_throw",
                context={"ability": "dexterity", "dc": 12},
            )
        )
    assert db.committed == 0


def test_request_player_roll_refuses_an_attack_kind():
    hero = GameObject(
        id="char-1",
        campaign_run_id="run-1",
        kind="creature",
        template_id=None,
        instance_key="pc:1",
        name="Hero",
        member_id="mem-1",
        state={"abilities": {}},
    )
    db = FakeSession(
        FakeResult(scalar=hero), FakeResult(scalar=_member()), FakeResult(scalar=_run())
    )

    with pytest.raises(ValueError, match="attack"):
        asyncio.run(
            service.request_player_roll(
                db, user_id="user-1", actor_id="char-1", kind="attack", context={}
            )
        )
    assert db.committed == 0


def test_request_player_roll_refuses_a_custom_expression_with_no_dice():
    # ← the "Roll 10" case: a bare constant produced a button with nothing
    # to roll.
    hero = GameObject(
        id="char-1",
        campaign_run_id="run-1",
        kind="creature",
        template_id=None,
        instance_key="pc:1",
        name="Hero",
        member_id="mem-1",
        state={"abilities": {}},
    )
    db = FakeSession(
        FakeResult(scalar=hero), FakeResult(scalar=_member()), FakeResult(scalar=_run())
    )

    with pytest.raises(ValueError, match="not a roll"):
        asyncio.run(
            service.request_player_roll(
                db,
                user_id="user-1",
                actor_id="char-1",
                kind="custom",
                context={"expression": "10"},
            )
        )
    assert db.committed == 0


# --- the real thing: real lair-maw content, three identical goblins -------


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _reach_lair_maw(db: AsyncSession, *, username: str):
    user_id = generate_id()
    await _insert_user(db, user_id, username=username)
    await db.commit()

    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id)
    await service.enter_adventure(db, user_id=user_id, run_id=run.id)
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-thornway")
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-lair-maw")
    return user_id, run, character


@pytest.mark.database
def test_describe_scene_creatures_tells_three_identical_goblins_apart(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="scene-lookup")

        described = await service.describe_scene_creatures(
            playthrough_db, run_id=run.id, scene_id="lair-maw"
        )

        goblins = [c for c in described if c["name"] == "Goblin Raider"]
        assert len(goblins) == 3
        # Id first, and each one is its own row (never merged by name).
        assert len({g["id"] for g in goblins}) == 3
        for goblin in goblins:
            assert goblin["role"] == "monster"
            assert goblin["is_alive"] is True
            assert set(goblin["attacks"]) == {"Rusty Shortsword", "Sling"}

        hero = next(c for c in described if c["id"] == character.id)
        assert hero["role"] == "player"

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_actor_ref_picks_the_first_living_goblin_by_id(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="ref-lookup")

        goblins_result = await playthrough_db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id AND name = 'Goblin Raider' "
                "AND scene_id = 'lair-maw' ORDER BY id"
            ),
            {"run_id": run.id},
        )
        goblin_ids = [row[0] for row in goblins_result.all()]
        assert len(goblin_ids) == 3

        # An exact id always wins outright, even though "Goblin" alone is
        # ambiguous among the three.
        resolved = await service.resolve_actor_ref(playthrough_db, run_id=run.id, ref=goblin_ids[1])
        assert resolved.id == goblin_ids[1]

        # By name, the first (lowest id) living one is used.
        resolved = await service.resolve_actor_ref(
            playthrough_db, run_id=run.id, ref="goblin raider"
        )
        assert resolved.id == goblin_ids[0]

        # A dead one is skipped by name -- it can no longer act.
        await playthrough_db.execute(
            text("UPDATE objects SET is_alive = false WHERE id = :id"), {"id": goblin_ids[0]}
        )
        await playthrough_db.commit()
        resolved = await service.resolve_actor_ref(
            playthrough_db, run_id=run.id, ref="goblin raider"
        )
        assert resolved.id == goblin_ids[1]

        # Nothing named this exists, alive or not.
        with pytest.raises(GameObjectNotFoundError):
            await service.resolve_actor_ref(playthrough_db, run_id=run.id, ref="Owlbear")

    asyncio.run(_scenario())
