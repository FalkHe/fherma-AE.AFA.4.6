"""WI1 (sprint 011/02): settling initiative -- one roll per side, then a
stable winner and actor order (intent §1.3, AC1/AC2).

`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content: the seed
character (Dexterity 12, modifier +1) and the `goblin`s (Dexterity 14,
modifier +2) placed in `lair-maw`, reached the same way the module's other
service suites do: `village-green` -> `thornway` -> `lair-maw`.

No `pytest-asyncio` (`AGENTS.md` gotchas): every async call in one scenario
is wrapped in a single `asyncio.run(...)`.
"""

import asyncio
import random as random_module

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service

CAMPAIGN_ID = "greenhollow"
GOBLIN_TEMPLATE = "goblin"


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call -- the same seam
    every other acceptance/service suite in this module uses, so a roll's
    `total` is a known number rather than a real one."""

    def __init__(self, faces: list[int]) -> None:
        super().__init__()
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - scripted, bounds ignored
        return self._faces.pop(0)


async def _insert_user(db: AsyncSession, user_id: str, *, username: str) -> None:
    await db.execute(
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


async def _goblin_ids(db: AsyncSession, *, run_id: str) -> list[str]:
    rows = (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id ORDER BY id"
            ),
            {"run_id": run_id, "template_id": GOBLIN_TEMPLATE},
        )
    ).all()
    return [row.id for row in rows]


async def _initiative_roll_count(db: AsyncSession, run_id: str) -> int:
    return (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'roll' AND payload->>'kind' = 'initiative'"
            ),
            {"run_id": run_id},
        )
    ).scalar_one()


@pytest.mark.database
def test_exactly_two_rolls_are_written_per_fight(playthrough_db):
    # <- AC1
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="init-count")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)

        with pytest.MonkeyPatch.context() as mp:
            shared_rng = _ScriptedRandom([15, 8])
            mp.setattr(playthrough_dice, "_rng", lambda: shared_rng)
            result = await service.settle_initiative(
                playthrough_db,
                user_id=user_id,
                run_id=run.id,
                hero_ids=[character.id],
                hostile_ids=goblin_ids,
            )

        assert await _initiative_roll_count(playthrough_db, run.id) == 2
        assert result.hero_roll_id != result.hostile_roll_id

    asyncio.run(_scenario())


@pytest.mark.database
def test_equal_totals_the_hero_side_wins_and_goes_first(playthrough_db):
    # <- AC2
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="init-tie")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)

        # Character Dexterity modifier +1, goblin +2: face 10 vs 9 ties
        # both totals at 11.
        with pytest.MonkeyPatch.context() as mp:
            shared_rng = _ScriptedRandom([10, 9])
            mp.setattr(playthrough_dice, "_rng", lambda: shared_rng)
            result = await service.settle_initiative(
                playthrough_db,
                user_id=user_id,
                run_id=run.id,
                hero_ids=[character.id],
                hostile_ids=goblin_ids,
            )

        assert result.hero_total == result.hostile_total
        assert result.winning_side == "hero"
        assert result.order == [character.id, *goblin_ids]

    asyncio.run(_scenario())


@pytest.mark.database
def test_order_is_stable_and_winner_first(playthrough_db):
    # <- AC1, AC2: within a side the given id order is kept.
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="init-order")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)

        with pytest.MonkeyPatch.context() as mp:
            shared_rng = _ScriptedRandom([1, 1])
            mp.setattr(playthrough_dice, "_rng", lambda: shared_rng)
            result = await service.settle_initiative(
                playthrough_db,
                user_id=user_id,
                run_id=run.id,
                hero_ids=[character.id],
                hostile_ids=goblin_ids,
            )

        # The goblins' outright roll (face 1, modifier +2 = 3) always beats
        # a character rolled low (face 1, modifier +1 = 2): hostile side
        # wins, its own given id order preserved, hero side following.
        assert result.winning_side == "hostile"
        assert result.order == [*goblin_ids, character.id]

    asyncio.run(_scenario())
