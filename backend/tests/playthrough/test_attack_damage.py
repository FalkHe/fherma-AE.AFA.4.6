"""WI2 (sprint 011/02): the typed halves of a fight -- `attack` returning
an `AttackResult` naming its own hit id instead of a bare outcome string,
`damage` returning a `DamageResult`, and a critical hit doubling the
attack's own dice, never its flat modifier (intent §1.4, AC3).

Minimal by design (← brief): the gate order, refusals and hp-clamp/alive-
split behaviours `attack`/`damage` share with every other mechanic already
have their own coverage in `test_service_attack_and_damage.py`; this file
covers only what changed -- the shape of what comes back, and the crit
doubling rule.

`@pytest.mark.database`, against the shared scratch-database fixture and
the real shipped `greenhollow/v1` content, the same fixture path
`test_service_attack_and_damage.py` uses (`village-green` -> `thornway` ->
`lair-maw`, the seed character's own `shepherds-knife`, +4/1d4+2, against
the `goblin`, AC 13, 7 hp).

No `pytest-asyncio` (`AGENTS.md` gotchas): every async call in one
scenario is wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest

from app.core.ids import generate_id
from app.modules.playthrough import service
from tests.playthrough.test_service_attack_and_damage import (
    KNIFE_TEMPLATE,
    _goblin_ids,
    _object_row,
    _owned_object_id,
    _reach_lair_maw,
    _rolled,
    _set_current_hp,
)


@pytest.mark.database
def test_attack_hit_lets_damage_apply_against_the_landed_hit(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="wi2-hit")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        # goblin AC 13; face 15 + to_hit 4 = 19, a plain hit.
        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=15,
            turn_id=turn_id,
        )
        attack_result = await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        assert attack_result.status == "hit"
        assert attack_result.hit_id is not None
        assert attack_result.total == 19
        assert attack_result.natural == 15
        assert attack_result.armour_class == 13

        # knife's own 1d4+2 damage; face 3 -> total 5.
        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=3,
            turn_id=turn_id,
        )
        damage_result = await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=goblin_id,
            roll_id=damage_roll.id,
            hit_id=attack_result.hit_id,
            turn_id=turn_id,
        )
        assert damage_result.applied == 5
        assert damage_result.current_hp == 2
        assert damage_result.max_hp == 7
        assert damage_result.is_alive is True
        assert damage_result.down is False

    asyncio.run(_scenario())


@pytest.mark.database
def test_attack_miss_names_no_hit_and_nothing_is_wounded(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="wi2-miss")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        # goblin AC 13; face 3 + to_hit 4 = 7, short of it.
        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=3,
            turn_id=turn_id,
        )
        attack_result = await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        assert attack_result.status == "miss"
        assert attack_result.hit_id is None

        before = await _object_row(playthrough_db, goblin_id)
        assert before.current_hp == 7

    asyncio.run(_scenario())


@pytest.mark.database
def test_critical_damage_doubles_dice_and_applies_the_modifier_once(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="wi2-crit")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        turn_id = generate_id()

        # The goblin's own Rusty Shortsword strikes the 12-hp character --
        # a natural 20 crits regardless of armour class, and the
        # character's own hp comfortably absorbs the doubled damage below
        # with no clamp muddying the assertion.
        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            kind="attack",
            context={"attack": "Rusty Shortsword"},
            face=20,
            turn_id=turn_id,
        )
        attack_result = await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            target_id=character.id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        assert attack_result.status == "critical"

        # Rusty Shortsword's own 1d6+2 damage; face 3 -- a normal roll
        # would apply 5, a critical doubles the die alone: 2*3 + 2 = 8,
        # never 2*5 = 10.
        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            kind="damage",
            context={"attack": "Rusty Shortsword"},
            face=3,
            turn_id=turn_id,
        )
        damage_result = await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=character.id,
            roll_id=damage_roll.id,
            hit_id=attack_result.hit_id,
            turn_id=turn_id,
            critical=True,
        )
        assert damage_result.applied == 8
        assert damage_result.current_hp == 4

    asyncio.run(_scenario())


@pytest.mark.database
def test_damage_to_zero_hp_downs_a_member_without_killing_them(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="wi2-down")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        # Lowered directly so a single hit brings the character to zero.
        await _set_current_hp(playthrough_db, character.id, 5)
        turn_id = generate_id()

        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            kind="attack",
            context={"attack": "Rusty Shortsword"},
            face=15,
            turn_id=turn_id,
        )
        attack_result = await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            target_id=character.id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        assert attack_result.status == "hit"

        # goblin's own 1d6+2 damage; face 6 -> total 8, more than 5 hp.
        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            kind="damage",
            context={"attack": "Rusty Shortsword"},
            face=6,
            turn_id=turn_id,
        )
        damage_result = await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=character.id,
            roll_id=damage_roll.id,
            hit_id=attack_result.hit_id,
            turn_id=turn_id,
        )
        assert damage_result.applied == 5
        assert damage_result.current_hp == 0
        assert damage_result.is_alive is True
        assert damage_result.down is True

        row = await _object_row(playthrough_db, character.id)
        assert row.current_hp == 0
        assert row.is_alive is True
        assert row.state["down"] is True

    asyncio.run(_scenario())
