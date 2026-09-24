"""WI1 (sprint 09): striking at somebody and hurting them -- `attack`
against the target's armour class, and `damage` bound to the attack
`tool_call` id that landed it (AC1, AC2, AC3's one-action half).

qa's own `test_acceptance_fight_in_the_transcript.py` drives the black-box
happy path against the sprint's interface contracts; this file covers the
gate order `attack` and `damage` share with every other mechanic in this
module (an unknown actor/target, an archived run), `attack`'s own three
refusals (already acted, target elsewhere, item not carried, a roll of
the wrong kind), the natural-20-regardless-of-armour-class rule, and
`damage`'s hit-binding refusals (a miss, another turn, a mismatched
target, spent twice) plus the hp clamp and the alive/down split.

`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content: the
seed character (AC 15, 12 hp, carrying `shepherds-knife`, +4/1d4+2) and
the `goblin` (AC 13, 7 hp, `Rusty Shortsword` +4/1d6+2, `Sling` +4/1d4+2)
placed three-deep in `lair-maw`, reached the same way
`test_service_interact.py` and qa's own suite do:
`village-green` -> `thornway` -> `lair-maw`.

No `pytest-asyncio` (`AGENTS.md` gotchas): every async call in one
scenario is wrapped in a single `asyncio.run(...)`.
"""

import asyncio
import os
import random as random_module

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.character.schemas import CharacterSheet, SheetItem
from app.modules.content.schemas import Abilities, Attack
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service
from app.modules.playthrough.errors import (
    AlreadyActedError,
    HitNotUsableError,
    ObjectNotReachableError,
    RollNotUsableError,
)
from app.modules.playthrough.models import GameObject

CAMPAIGN_ID = "greenhollow"
KNIFE_TEMPLATE = "shepherds-knife"
GOBLIN_TEMPLATE = "goblin"


def _sheet_born_sheet(*, name: str = "Mira Thistlewood") -> CharacterSheet:
    """A hand-built level-1 sheet (sprint 009-02, WI2, AC4/AC5) carrying
    one weapon whose to-hit/damage is already resolved into its own
    state, the way `character_service.build_sheet` would leave it."""
    return CharacterSheet(
        name=name,
        race="Human",
        character_class="Ranger",
        alignment="Chaotic Good",
        abilities=Abilities(
            strength=12, dexterity=16, constitution=14, intelligence=10, wisdom=13, charisma=8
        ),
        max_hp=11,
        armour_class=14,
        speed=30,
        saving_throws=["strength", "dexterity"],
        skills=["Survival", "Stealth"],
        equipment=[
            SheetItem(
                kind="weapon",
                id="shortsword",
                quantity=1,
                name="Sheet-Born Shortsword",
                attacks=[Attack(name="Sheet-Born Shortsword", to_hit=5, damage="1d6+3")],
            )
        ],
        proficiency_bonus=2,
        appearance="Lean and travel-worn.",
        backstory="Grew up tracking game through the Greenhollow.",
    )


async def _reach_lair_maw_with_sheet(db: AsyncSession, *, username: str, sheet: CharacterSheet):
    user_id = generate_id()
    await _insert_user(db, user_id, username=username)
    await db.commit()

    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id, sheet=sheet)
    await service.enter_adventure(db, user_id=user_id, run_id=run.id)
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-thornway")
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-lair-maw")
    return user_id, run, character


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call -- the same seam
    and subclass every other acceptance/service suite in this module uses,
    so a roll's `total` is a known number rather than a real one."""

    def __init__(self, faces: list[int]) -> None:
        super().__init__()
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - scripted, bounds ignored
        return self._faces.pop(0)


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _second_connection:
    """An independent connection to the same scratch database, opened only
    after a refusing call has already raised -- proves the refusal is
    genuinely committed rather than merely flushed into the writer's own
    still-open transaction (the same helper every other acceptance/service
    suite in this module keeps its own copy of)."""

    async def __aenter__(self):
        self._engine = create_async_engine(os.environ["DATABASE_URL"])
        sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._session = sessionmaker()
        return self._session

    async def __aexit__(self, *exc_info) -> None:
        await self._session.close()
        await self._engine.dispose()


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


async def _owned_object_id(db: AsyncSession, *, owner_id: str, template_id: str) -> str:
    return (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE owner_object_id = :owner_id "
                "AND template_id = :template_id LIMIT 1"
            ),
            {"owner_id": owner_id, "template_id": template_id},
        )
    ).scalar_one()


async def _owned_object_id_by_name(db: AsyncSession, *, owner_id: str, name: str) -> str:
    """A carried row with no template of its own (sprint 009-02, WI2, AC5)
    -- found by name, since there is no `template_id` to look it up by."""
    return (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE owner_object_id = :owner_id "
                "AND template_id IS NULL AND name = :name LIMIT 1"
            ),
            {"owner_id": owner_id, "name": name},
        )
    ).scalar_one()


async def _miras_object_id(db: AsyncSession, *, run_id: str, template_id: str) -> str:
    """Mira's own carried instance of `template_id` -- distinct from the
    seed character's own copy of the same `shepherds-knife` template."""
    return (
        await db.execute(
            text(
                "SELECT o.id FROM objects o JOIN objects owner "
                "ON o.owner_object_id = owner.id "
                "WHERE o.campaign_run_id = :run_id AND o.template_id = :template_id "
                "AND owner.template_id = 'mira'"
            ),
            {"run_id": run_id, "template_id": template_id},
        )
    ).scalar_one()


async def _object_row(db: AsyncSession, object_id: str):
    return (
        await db.execute(
            text(
                "SELECT current_hp, armour_class, is_alive, member_id, state "
                "FROM objects WHERE id = :id"
            ),
            {"id": object_id},
        )
    ).one()


async def _set_current_hp(db: AsyncSession, object_id: str, hp: int) -> None:
    # Through the ORM, on the same identity-mapped instance a caller may
    # already hold a reference to (e.g. the scenario's own `character`) --
    # a raw `UPDATE` would leave that instance's cached attribute stale,
    # since this session's `expire_on_commit` is `False`.
    obj = (await db.execute(select(GameObject).where(GameObject.id == object_id))).scalar_one()
    obj.current_hp = hp
    await db.commit()


async def _set_armour_class(db: AsyncSession, object_id: str, armour_class: int) -> None:
    obj = (await db.execute(select(GameObject).where(GameObject.id == object_id))).scalar_one()
    obj.armour_class = armour_class
    await db.commit()


async def _tool_calls(db: AsyncSession, run_id: str, *, result: str, name: str) -> list[dict]:
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
        if row.payload["result"] == result and row.payload["name"] == name
    ]


async def _rolled(db, *, user_id, actor_id, kind, context, face, visibility="dm", turn_id=None):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([face]))
        return await service.roll(
            db,
            user_id=user_id,
            actor_id=actor_id,
            kind=kind,
            context=context,
            visibility=visibility,
            turn_id=turn_id,
        )


# --- attack -----------------------------------------------------------------


@pytest.mark.database
def test_attack_from_a_monsters_own_stat_block_needs_no_item(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="attack-monster")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        turn_id = generate_id()

        # character AC 15; face 15 + to_hit 4 = 19.
        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            kind="attack",
            context={"attack": "Rusty Shortsword"},
            face=15,
            turn_id=turn_id,
        )

        outcome = await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            target_id=character.id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        assert outcome.status == "hit"

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="attack")
        assert "itemId" not in ok_calls[0]["args"]
        assert ok_calls[0]["args"] == {
            "actorId": goblin_id,
            "targetId": character.id,
            "rollId": attack_roll.id,
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_attack_refuses_a_second_attack_by_the_same_actor_this_turn(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(
            playthrough_db, username="attack-already-acted"
        )
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        first_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=15,
            turn_id=turn_id,
        )
        await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=first_roll.id,
            turn_id=turn_id,
        )

        second_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=15,
            turn_id=turn_id,
        )
        with pytest.raises(AlreadyActedError) as excinfo:
            await service.attack(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                target_id=goblin_id,
                item_id=knife_id,
                roll_id=second_roll.id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.ALREADY_ACTED

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="attack")
            assert len(refused) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_attack_refuses_a_target_in_another_scene(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="attack-far-target")
        await playthrough_db.commit()

        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)
        await service.enter_adventure(playthrough_db, user_id=user_id, run_id=run.id)
        # The character stays at `village-green`; the goblins are three
        # scenes away at `lair-maw`.
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=15,
            turn_id=turn_id,
        )

        with pytest.raises(ObjectNotReachableError) as excinfo:
            await service.attack(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                target_id=goblin_id,
                item_id=knife_id,
                roll_id=attack_roll.id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.OBJECT_NOT_REACHABLE

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="attack")
            assert len(refused) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_attack_refuses_an_item_the_actor_does_not_carry(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(
            playthrough_db, username="attack-unheld-item"
        )
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        # Mira's own copy of the same template the character carries --
        # owned by Mira, not by this actor.
        miras_knife_id = await _miras_object_id(
            playthrough_db, run_id=run.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=15,
            turn_id=turn_id,
        )

        with pytest.raises(ObjectNotReachableError) as excinfo:
            await service.attack(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                target_id=goblin_id,
                item_id=miras_knife_id,
                roll_id=attack_roll.id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.OBJECT_NOT_REACHABLE

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="attack")
            assert len(refused) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_attack_refuses_a_roll_of_the_wrong_kind(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(
            playthrough_db, username="attack-wrong-roll"
        )
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        wrong_kind_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="initiative",
            context={},
            face=10,
            turn_id=turn_id,
        )

        with pytest.raises(RollNotUsableError) as excinfo:
            await service.attack(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                target_id=goblin_id,
                item_id=knife_id,
                roll_id=wrong_kind_roll.id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.ROLL_NOT_USABLE

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="attack")
            assert len(refused) == 1

    asyncio.run(_scenario())


# --- damage -------------------------------------------------------------


async def _hit(db, *, user_id, run_id, actor_id, target_id, item_id, face, turn_id):
    """One successful `attack` (`hit` or `crit`), returning its own
    `tool_call` event id -- `damage`'s `hit_id`."""
    context = {"item_id": KNIFE_TEMPLATE} if item_id is not None else {"attack": "Rusty Shortsword"}
    attack_roll = await _rolled(
        db,
        user_id=user_id,
        actor_id=actor_id,
        kind="attack",
        context=context,
        face=face,
        turn_id=turn_id,
    )
    await service.attack(
        db,
        user_id=user_id,
        actor_id=actor_id,
        target_id=target_id,
        item_id=item_id,
        roll_id=attack_roll.id,
        turn_id=turn_id,
    )
    event_id = (
        await db.execute(
            text(
                "SELECT id FROM events WHERE campaign_run_id = :run_id AND type = 'tool_call' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"run_id": run_id},
        )
    ).scalar_one()
    return event_id


@pytest.mark.database
def test_damage_lowers_hp_and_clamps_at_zero_killing_a_memberless_creature(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="damage-kill")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        hit_id = await _hit(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            face=15,
            turn_id=turn_id,
        )

        # goblin's own 1d4+2 damage; face 6 -> total 8, more than its 7 hp.
        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=6,
            turn_id=turn_id,
        )

        applied = await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=goblin_id,
            roll_id=damage_roll.id,
            hit_id=hit_id,
            turn_id=turn_id,
        )
        assert applied.applied == 7

        row = await _object_row(playthrough_db, goblin_id)
        assert row.current_hp == 0
        assert row.is_alive is False

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="damage")
        assert len(ok_calls) == 1
        assert ok_calls[0]["args"] == {
            "targetId": goblin_id,
            "rollId": damage_roll.id,
            "hitId": hit_id,
        }
        assert ok_calls[0]["outcome"] == {
            "rolled": 8,
            "applied": 7,
            "currentHp": 0,
            "isAlive": False,
            "down": False,
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_damage_leaves_a_character_alive_and_down_at_zero_hp(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="damage-down")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        # Lowered directly so a single hit can bring the character to
        # zero: the shipped goblin's own damage die tops out at 8, well
        # under the seed character's 12 hp.
        await _set_current_hp(playthrough_db, character.id, 5)
        turn_id = generate_id()

        hit_id = await _hit(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            actor_id=goblin_id,
            target_id=character.id,
            item_id=None,
            face=15,
            turn_id=turn_id,
        )

        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            kind="damage",
            context={"attack": "Rusty Shortsword"},
            face=6,
            turn_id=turn_id,
        )

        applied = await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=character.id,
            roll_id=damage_roll.id,
            hit_id=hit_id,
            turn_id=turn_id,
        )
        assert applied.applied == 5

        row = await _object_row(playthrough_db, character.id)
        assert row.current_hp == 0
        assert row.is_alive is True
        assert row.state["down"] is True

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="damage")
        assert ok_calls[0]["outcome"] == {
            "rolled": 8,
            "applied": 5,
            "currentHp": 0,
            "isAlive": True,
            "down": True,
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_damage_refuses_a_hit_that_was_a_miss(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="damage-miss")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=3,
            turn_id=turn_id,
        )
        await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        miss_id = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call' ORDER BY id DESC LIMIT 1"
                ),
                {"run_id": run.id},
            )
        ).scalar_one()

        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,
            turn_id=turn_id,
        )

        with pytest.raises(HitNotUsableError) as excinfo:
            await service.damage(
                playthrough_db,
                user_id=user_id,
                target_id=goblin_id,
                roll_id=damage_roll.id,
                hit_id=miss_id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.HIT_NOT_USABLE

        row = await _object_row(playthrough_db, goblin_id)
        assert row.current_hp == 7

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="damage")
            assert len(refused) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_damage_refuses_a_hit_from_another_turn(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="damage-turn")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        attack_turn = generate_id()
        other_turn = generate_id()

        hit_id = await _hit(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            face=15,
            turn_id=attack_turn,
        )

        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,
            turn_id=other_turn,
        )

        with pytest.raises(HitNotUsableError) as excinfo:
            await service.damage(
                playthrough_db,
                user_id=user_id,
                target_id=goblin_id,
                roll_id=damage_roll.id,
                hit_id=hit_id,
                turn_id=other_turn,
            )
        assert excinfo.value.code == ErrorCode.HIT_NOT_USABLE

        row = await _object_row(playthrough_db, goblin_id)
        assert row.current_hp == 7

    asyncio.run(_scenario())


@pytest.mark.database
def test_damage_refuses_a_target_argument_that_mismatches_the_hits_own_target(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="damage-mismatch")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)
        struck_goblin, other_goblin = goblin_ids[0], goblin_ids[1]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        hit_id = await _hit(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            actor_id=character.id,
            target_id=struck_goblin,
            item_id=knife_id,
            face=15,
            turn_id=turn_id,
        )

        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,
            turn_id=turn_id,
        )

        with pytest.raises(HitNotUsableError) as excinfo:
            await service.damage(
                playthrough_db,
                user_id=user_id,
                target_id=other_goblin,
                roll_id=damage_roll.id,
                hit_id=hit_id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.HIT_NOT_USABLE

        row = await _object_row(playthrough_db, other_goblin)
        assert row.current_hp == 7

    asyncio.run(_scenario())


@pytest.mark.database
def test_damage_refuses_the_same_hit_spent_twice(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="damage-twice")
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        hit_id = await _hit(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            face=15,
            turn_id=turn_id,
        )

        first_damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=2,
            turn_id=turn_id,
        )
        await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=goblin_id,
            roll_id=first_damage_roll.id,
            hit_id=hit_id,
            turn_id=turn_id,
        )

        second_damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=2,
            turn_id=turn_id,
        )
        with pytest.raises(HitNotUsableError) as excinfo:
            await service.damage(
                playthrough_db,
                user_id=user_id,
                target_id=goblin_id,
                roll_id=second_damage_roll.id,
                hit_id=hit_id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.HIT_NOT_USABLE

        row = await _object_row(playthrough_db, goblin_id)
        assert row.current_hp == 3  # only the first damage ever applied

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="damage")
            assert len(refused) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_damage_refuses_a_roll_of_the_wrong_kind(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(
            playthrough_db, username="damage-wrong-roll"
        )
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        hit_id = await _hit(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            face=15,
            turn_id=turn_id,
        )

        # An `attack` roll offered where a `damage` roll belongs.
        wrong_kind_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=10,
            turn_id=turn_id,
        )

        with pytest.raises(RollNotUsableError) as excinfo:
            await service.damage(
                playthrough_db,
                user_id=user_id,
                target_id=goblin_id,
                roll_id=wrong_kind_roll.id,
                hit_id=hit_id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.ROLL_NOT_USABLE

        row = await _object_row(playthrough_db, goblin_id)
        assert row.current_hp == 7

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="damage")
            assert len(refused) == 1

    asyncio.run(_scenario())


# --- sprint 009-02, WI2: a built sheet's full state and its own gear -----


@pytest.mark.database
def test_ac4_a_sheet_born_characters_full_state_survives_a_damage_write_back(playthrough_db):
    async def _scenario():
        sheet = _sheet_born_sheet()
        user_id, run, character = await _reach_lair_maw_with_sheet(
            playthrough_db, username="sheet-state", sheet=sheet
        )
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        turn_id = generate_id()

        # The goblin's own Rusty Shortsword (+4/1d6+2) brings the sheet's
        # 11 hp to exactly 0: face 15 (total 19) hits the sheet's AC 14;
        # face 9 (total 11) applies all 11 remaining hit points.
        hit_id = await _hit(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            actor_id=goblin_id,
            target_id=character.id,
            item_id=None,
            face=15,
            turn_id=turn_id,
        )
        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=goblin_id,
            kind="damage",
            context={"attack": "Rusty Shortsword"},
            face=9,
            turn_id=turn_id,
        )

        applied = await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=character.id,
            roll_id=damage_roll.id,
            hit_id=hit_id,
            turn_id=turn_id,
        )
        assert applied.applied == 11

        row = await _object_row(playthrough_db, character.id)
        assert row.current_hp == 0
        assert row.is_alive is True

        state = row.state
        assert state["down"] is True
        assert state["level"] == 1
        assert state["alignment"] == "Chaotic Good"
        assert state["speed"] == 30
        assert state["proficiency_bonus"] == 2
        assert state["saving_throws"] == ["strength", "dexterity"]
        assert state["skills"] == ["Survival", "Stealth"]
        assert state["background"] == sheet.backstory
        assert len(state["equipment"]) == 1
        assert state["equipment"][0]["name"] == "Sheet-Born Shortsword"
        assert state["equipment"][0]["attacks"][0]["to_hit"] == 5

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac5_attack_resolves_from_a_carried_rows_own_state_and_a_template_item_still_works(
    playthrough_db,
):
    async def _scenario():
        # A sheet-born weapon row: to-hit/damage read from its own carried
        # state, never a content template (there is none).
        sheet = _sheet_born_sheet()
        user_id, run, character = await _reach_lair_maw_with_sheet(
            playthrough_db, username="sheet-attack", sheet=sheet
        )
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        weapon_id = await _owned_object_id_by_name(
            playthrough_db, owner_id=character.id, name="Sheet-Born Shortsword"
        )
        turn_id = generate_id()

        # goblin AC 13; item's own to_hit +5, face 10 -> total 15, a hit.
        attack_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": weapon_id},
            face=10,
            turn_id=turn_id,
        )
        assert attack_roll.payload["formula"] == "1d20+5"

        outcome = await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=weapon_id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        assert outcome.status == "hit"

        damage_roll = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": weapon_id},
            face=4,
            turn_id=turn_id,
        )
        assert damage_roll.payload["formula"] == "1d6+3"

        # The seed hero's `shepherds-knife` uses its carried-row ID, which
        # is the ID the game context exposes to the DM.
        seed_user_id, seed_run, seed_character = await _reach_lair_maw(
            playthrough_db, username="seed-still-works"
        )
        seed_goblin_id = (await _goblin_ids(playthrough_db, run_id=seed_run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=seed_character.id, template_id=KNIFE_TEMPLATE
        )
        seed_turn_id = generate_id()

        seed_attack_roll = await _rolled(
            playthrough_db,
            user_id=seed_user_id,
            actor_id=seed_character.id,
            kind="attack",
            context={"item_id": knife_id},
            face=15,
            turn_id=seed_turn_id,
        )
        assert seed_attack_roll.payload["formula"] == "1d20+4"

        seed_outcome = await service.attack(
            playthrough_db,
            user_id=seed_user_id,
            actor_id=seed_character.id,
            target_id=seed_goblin_id,
            item_id=knife_id,
            roll_id=seed_attack_roll.id,
            turn_id=seed_turn_id,
        )
        assert seed_outcome.status == "hit"

    asyncio.run(_scenario())
