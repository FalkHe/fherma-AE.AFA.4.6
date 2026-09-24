"""WI2 (sprint 010/04): every world-changing mechanic leaves a
player-visible transcript entry carrying who, what and the numbers before
and after; refusals and private mechanics leave none (AC2, half of AC3).

Covers the six write sites `plan.md`'s interface I2 names: `take`/`drop`/
`give` append `item_moved`, `damage` appends `hp_changed`, `interact`
appends `way_opened` on success only, `use_exit` and `enter_adventure`
append `scene_entered` carrying the destination's title. Plus WI2's own
`record_rule_lookup`. Not a black-box qa suite -- reads `events.payload`
straight off the shared scratch database, the same way
`test_service_inventory_moves.py` and `test_service_attack_and_damage.py`
already do.

`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content, walking
the same path every other WI1/WI2 service suite in this module does:
`village-green` -> `thornway` -> `lair-maw`, where the goblins and
`thorn-screen` stand.

No `pytest-asyncio` (AGENTS.md gotchas): every async call in one scenario
is wrapped in a single `asyncio.run(...)`.
"""

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service
from app.modules.playthrough.errors import CampaignRunNotFoundError

CAMPAIGN_ID = "greenhollow"
KNIFE_TEMPLATE = "shepherds-knife"
LIFT_ACTION = (
    "Lift the lashed brush aside a branch at a time, without letting it scrape on the stone"
)
LIFT_DC = 13


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _ScriptedRandom:
    """A fixed, pre-scripted sequence of face values, one per call -- the
    same seam every other service suite in this module uses."""

    def __init__(self, faces: list[int]) -> None:
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - scripted, bounds ignored
        return self._faces.pop(0)


async def _rolled(db, *, user_id, actor_id, kind, context, face, turn_id=None):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([face]))
        return await service.roll(
            db, user_id=user_id, actor_id=actor_id, kind=kind, context=context, turn_id=turn_id
        )


async def _new_run(db: AsyncSession, *, username: str):
    user_id = generate_id()
    await _insert_user(db, user_id, username=username)
    await db.commit()

    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id)
    return user_id, run, character


async def _reach_village_green(db: AsyncSession, *, username: str):
    user_id, run, character = await _new_run(db, username=username)
    await service.enter_adventure(db, user_id=user_id, run_id=run.id)
    return user_id, run, character


async def _reach_lair_maw(db: AsyncSession, *, username: str):
    user_id, run, character = await _reach_village_green(db, username=username)
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-thornway")
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-lair-maw")

    fixture_id = (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = 'thorn-screen'"
            ),
            {"run_id": run.id},
        )
    ).scalar_one()

    return user_id, run, character, fixture_id


async def _object_id(db: AsyncSession, *, run_id: str, template_id: str) -> str:
    return (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id LIMIT 1"
            ),
            {"run_id": run_id, "template_id": template_id},
        )
    ).scalar_one()


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


async def _goblin_ids(db: AsyncSession, *, run_id: str) -> list[str]:
    rows = (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = 'goblin' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [row.id for row in rows]


async def _player_events(db: AsyncSession, run_id: str, *, type_: str) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = :type AND visibility = 'player' ORDER BY id"
            ),
            {"run_id": run_id, "type": type_},
        )
    ).all()
    return [row.payload for row in rows]


async def _all_visible_event_count(db: AsyncSession, run_id: str) -> int:
    return (
        await db.execute(
            text(
                "SELECT count(*) FROM events WHERE campaign_run_id = :run_id "
                "AND visibility = 'player'"
            ),
            {"run_id": run_id},
        )
    ).scalar_one()


async def _latest_tool_call_id(db: AsyncSession, run_id: str) -> str:
    return (
        await db.execute(
            text(
                "SELECT id FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' ORDER BY id DESC LIMIT 1"
            ),
            {"run_id": run_id},
        )
    ).scalar_one()


# --- item_moved: take / drop / give -----------------------------------------


@pytest.mark.database
def test_take_appends_one_item_moved_entry_naming_hero_and_item(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="visible-take"
        )
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")

        await service.take(
            playthrough_db, user_id=user_id, actor_id=character.id, item_id=horseshoe_id
        )

        visible = await _player_events(playthrough_db, run.id, type_="item_moved")
        assert len(visible) == 1
        assert visible[0] == {
            "movement": "taken",
            "actorId": character.id,
            "actorName": character.name,
            "itemId": horseshoe_id,
            "itemName": "Bent Horseshoe",
            "toId": None,
            "toName": None,
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_drop_appends_one_item_moved_entry_naming_hero_and_item(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="visible-drop"
        )
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        turn_id = generate_id()

        await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=turn_id,
        )
        await service.drop(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=turn_id,
        )

        visible = await _player_events(playthrough_db, run.id, type_="item_moved")
        assert len(visible) == 2  # the take, then the drop
        dropped = visible[-1]
        assert dropped["movement"] == "dropped"
        assert dropped["actorId"] == character.id
        assert dropped["actorName"] == character.name
        assert dropped["itemId"] == horseshoe_id
        assert dropped["itemName"] == "Bent Horseshoe"
        assert dropped["toId"] is None
        assert dropped["toName"] is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_give_appends_one_item_moved_entry_naming_the_recipient(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="visible-give"
        )
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        mira_id = await _object_id(playthrough_db, run_id=run.id, template_id="mira")

        await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=generate_id(),
        )
        await service.give(
            playthrough_db,
            user_id=user_id,
            from_id=character.id,
            to_id=mira_id,
            item_id=horseshoe_id,
            turn_id=generate_id(),
        )

        visible = await _player_events(playthrough_db, run.id, type_="item_moved")
        given = visible[-1]
        assert given == {
            "movement": "given",
            "actorId": character.id,
            "actorName": character.name,
            "itemId": horseshoe_id,
            "itemName": "Bent Horseshoe",
            "toId": mira_id,
            "toName": "Mira",
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_refused_take_leaves_no_item_moved_entry(playthrough_db):
    async def _scenario():
        user_id, run, character, _fixture_id = await _reach_lair_maw(
            playthrough_db, username="visible-refused-take"
        )
        # `bent-horseshoe` stands at `village-green`, three scenes away.
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")

        result = await service.take(
            playthrough_db, user_id=user_id, actor_id=character.id, item_id=horseshoe_id
        )
        assert result.status == "refused"

        visible = await _player_events(playthrough_db, run.id, type_="item_moved")
        assert visible == []

    asyncio.run(_scenario())


# --- hp_changed: damage ------------------------------------------------------


@pytest.mark.database
def test_damage_appends_one_hp_changed_entry_with_before_after_and_flags(playthrough_db):
    async def _scenario():
        user_id, run, character, _fixture_id = await _reach_lair_maw(
            playthrough_db, username="visible-damage"
        )
        goblin_id = (await _goblin_ids(playthrough_db, run_id=run.id))[0]
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )
        turn_id = generate_id()

        # goblin AC 13; face 15 + to_hit 4 = 19, a hit.
        attack_roll = await _rolled(
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
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        hit_id = await _latest_tool_call_id(playthrough_db, run.id)

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

        visible = await _player_events(playthrough_db, run.id, type_="hp_changed")
        assert len(visible) == 1
        assert visible[0] == {
            "targetId": goblin_id,
            "targetName": "Goblin Raider",
            "before": 7,
            "after": 0,
            "maxHp": 7,
            "alive": False,
            "down": False,
        }

    asyncio.run(_scenario())


# --- way_opened: interact, on success only -----------------------------------


@pytest.mark.database
def test_interact_appends_one_way_opened_entry_on_a_successful_check(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="visible-interact-pass"
        )

        # Strength +2 (score 15); a face of 11 totals exactly the dc.
        roll_event = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=11,
        )

        result = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=LIFT_ACTION,
            roll_id=roll_event.id,
        )
        assert result.status == "ok"
        assert result.facts["success"] is True

        visible = await _player_events(playthrough_db, run.id, type_="way_opened")
        assert len(visible) == 1
        assert visible[0] == {
            "actorId": character.id,
            "actorName": character.name,
            "objectId": fixture_id,
            "objectName": "Screen of Thornbrush",
            "action": LIFT_ACTION,
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_interact_appends_no_way_opened_entry_when_the_check_fails(playthrough_db):
    async def _scenario():
        user_id, run, character, fixture_id = await _reach_lair_maw(
            playthrough_db, username="visible-interact-fail"
        )

        # Strength +2; a face of 1 totals 3, well under the dc of 13.
        roll_event = await _rolled(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=1,
        )

        result = await service.interact(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            object_id=fixture_id,
            action=LIFT_ACTION,
            roll_id=roll_event.id,
        )
        assert result.status == "ok"
        assert result.facts["success"] is False

        visible = await _player_events(playthrough_db, run.id, type_="way_opened")
        assert visible == []

    asyncio.run(_scenario())


# --- scene_entered: use_exit and enter_adventure carry a title ---------------


@pytest.mark.database
def test_enter_adventure_appends_a_scene_entered_entry_carrying_the_entry_scenes_title(
    playthrough_db,
):
    async def _scenario():
        user_id, run, _character = await _new_run(playthrough_db, username="visible-enter")

        adventure_run = await service.enter_adventure(
            playthrough_db, user_id=user_id, run_id=run.id
        )

        visible = await _player_events(playthrough_db, run.id, type_="scene_entered")
        assert len(visible) == 1
        assert visible[0] == {
            "adventureRunId": adventure_run.id,
            "sceneId": "village-green",
            "sceneTitle": "The Village Green",
        }

    asyncio.run(_scenario())


@pytest.mark.database
def test_use_exit_appends_a_scene_entered_entry_carrying_the_destinations_title(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="visible-exit"
        )

        await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id="to-thornway"
        )

        visible = await _player_events(playthrough_db, run.id, type_="scene_entered")
        # one from `enter_adventure`'s own opening scene, one from this move
        assert len(visible) == 2
        moved = visible[-1]
        assert moved["sceneId"] == "thornway"
        assert moved["sceneTitle"] == "The Thornway"

    asyncio.run(_scenario())


# --- AC3: private mechanics leave nothing visible ----------------------------


@pytest.mark.database
def test_a_successful_attack_leaves_no_visible_entry(playthrough_db):
    async def _scenario():
        user_id, run, character, _fixture_id = await _reach_lair_maw(
            playthrough_db, username="visible-private-attack"
        )
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

        before = await _all_visible_event_count(playthrough_db, run.id)

        outcome = await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=attack_roll.id,
            turn_id=turn_id,
        )
        assert outcome.status == "hit"

        after = await _all_visible_event_count(playthrough_db, run.id)
        assert after == before

    asyncio.run(_scenario())


# --- record_rule_lookup -------------------------------------------------------


@pytest.mark.database
def test_record_rule_lookup_appends_one_visible_entry_naming_the_topic(playthrough_db):
    async def _scenario():
        user_id, run, _character = await _new_run(playthrough_db, username="visible-rule-lookup")
        topic = "Chapter 7 › Using Ability Scores › Hiding"

        event = await service.record_rule_lookup(
            playthrough_db, user_id=user_id, run_id=run.id, topic=topic
        )

        assert event.type == "rule_looked_up"
        assert event.visibility == "player"
        assert event.payload == {"topic": topic}

        visible = await _player_events(playthrough_db, run.id, type_="rule_looked_up")
        assert visible == [{"topic": topic}]

    asyncio.run(_scenario())


@pytest.mark.database
def test_record_rule_lookup_raises_not_found_for_a_foreign_run(playthrough_db):
    async def _scenario():
        _user_id_a, run_a, _character_a = await _new_run(
            playthrough_db, username="visible-rule-lookup-a"
        )
        user_id_b, _run_b, _character_b = await _new_run(
            playthrough_db, username="visible-rule-lookup-b"
        )

        with pytest.raises(CampaignRunNotFoundError):
            await service.record_rule_lookup(
                playthrough_db, user_id=user_id_b, run_id=run_a.id, topic="Grappling"
            )

        visible = await _player_events(playthrough_db, run_a.id, type_="rule_looked_up")
        assert visible == []

    asyncio.run(_scenario())
