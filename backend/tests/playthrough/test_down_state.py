"""WI3 (sprint 011/02): one down-state rule agreeing in every mutation and
read (intent §1.5, AC4) -- a hero at 0 hp is downed even though `damage`
never flips a member's own `is_alive`. Covers `is_down` through its
callers: `describe_scene_creatures`, `character_read`, `resolve_actor_ref`
and `attack`'s own refusal, not `is_down` in isolation.

`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content, reaching
`lair-maw` exactly like `test_service_attack_and_damage.py` does --
`village-green` -> `thornway` -> `lair-maw`, where the seed hero and a
goblin share a scene.

No `pytest-asyncio` (`AGENTS.md` gotchas): every async call in one
scenario is wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.modules.playthrough import service
from app.modules.playthrough.errors import GameObjectNotFoundError, ObjectNotReachableError
from app.modules.playthrough.models import GameObject
from app.modules.playthrough.schemas import CharacterState

CAMPAIGN_ID = "greenhollow"
GOBLIN_TEMPLATE = "goblin"


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


async def _goblin_id(db: AsyncSession, *, run_id: str) -> str:
    row = (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id ORDER BY id LIMIT 1"
            ),
            {"run_id": run_id, "template_id": GOBLIN_TEMPLATE},
        )
    ).one()
    return row.id


async def _down_hero(db: AsyncSession, hero_id: str) -> None:
    """Writes the hero to 0 hp with `state.down = True` -- `damage`'s own
    write (`service.py`'s own `target.current_hp == 0` branch), reproduced
    directly so this suite tests the read side alone, not `attack`/
    `damage`'s already-covered write."""
    obj = (await db.execute(select(GameObject).where(GameObject.id == hero_id))).scalar_one()
    obj.current_hp = 0
    new_state = CharacterState.model_validate(obj.state).model_copy(update={"down": True})
    obj.state = new_state.model_dump()
    await db.commit()


@pytest.mark.database
def test_downed_hero_reported_down_in_scene_and_card(playthrough_db):
    async def scenario():
        db = playthrough_db
        user_id, run, character = await _reach_lair_maw(db, username="downed-scene")
        await _down_hero(db, character.id)

        creatures = await service.describe_scene_creatures(
            db, run_id=run.id, scene_id=character.scene_id
        )
        hero_entry = next(c for c in creatures if c["id"] == character.id)
        assert hero_entry["is_alive"] is True
        assert hero_entry["down"] is True

        character_row = (
            await db.execute(select(GameObject).where(GameObject.id == character.id))
        ).scalar_one()
        card = service.character_read(character_row)
        assert card.down is True
        assert card.current_hp == 0

    asyncio.run(scenario())


@pytest.mark.database
def test_downed_hero_not_resolvable_by_name(playthrough_db):
    async def scenario():
        db = playthrough_db
        user_id, run, character = await _reach_lair_maw(db, username="downed-resolve")
        await _down_hero(db, character.id)

        with pytest.raises(GameObjectNotFoundError):
            await service.resolve_actor_ref(db, run_id=run.id, ref=character.name)

    asyncio.run(scenario())


@pytest.mark.database
def test_downed_hero_cannot_attack_or_be_attacked(playthrough_db):
    async def scenario():
        db = playthrough_db
        user_id, run, character = await _reach_lair_maw(db, username="downed-attack")
        goblin_id = await _goblin_id(db, run_id=run.id)
        await _down_hero(db, character.id)

        with pytest.raises(ObjectNotReachableError):
            await service.attack(
                db,
                user_id=user_id,
                actor_id=character.id,
                target_id=goblin_id,
                roll_id=generate_id(),
            )

        with pytest.raises(ObjectNotReachableError):
            await service.attack(
                db,
                user_id=user_id,
                actor_id=goblin_id,
                target_id=character.id,
                roll_id=generate_id(),
            )

    asyncio.run(scenario())
