"""qa acceptance tests -- sprint 005/08b "items move between the floor, a
pack and a container"
(`docs/intents/005-game-state-services/sprints/08b-inventory-moves/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`'s
new `take`/`drop`/`give`/`use_item` or `.errors`' new codes -- those are
this sprint's own work items, written in parallel, and this file never
imports or reads them. Everything else driven here (`start_campaign_run`,
`create_character`, `enter_adventure`, `use_exit`) is earlier sprints',
already merged, used exactly as their own acceptance suites use it
(`test_acceptance_exits_and_endings.py`, `test_acceptance_interact_and_
one_action.py`).

Exercised against the shipped `greenhollow/v1` content (`backend/content/
campaigns/greenhollow/v1/`), read by template id rather than pasted as
literals-only guesses: `village-green` (the entry scene) carries a loose
`bent-horseshoe` on the ground and the creature `mira`, who already holds
her own `shepherds-knife`; the seed character's own starting pack (`
campaign.json`'s `seed_character.inventory`) carries a `shepherds-knife`
of its own -- a second, distinct row, never Mira's. Down the one path
`test_acceptance_exits_and_endings.py` and `test_acceptance_interact_and_
one_action.py` also walk (`village-green` -> `thornway` -> `lair-maw` ->
`lair-hollow`), `lair-hollow` carries the goblin boss holding a
`notched-cleaver` and a `wool-sack` fixture holding two `stolen-fleece`.

Every refusal's persisted `tool_call` record is read back from a
**second** connection to the same scratch database, opened only after the
refusing call has already raised -- never from the session that ran it, so
a merely-flushed row can never be mistaken for a genuinely committed one
(same pattern as the two acceptance files named above; copied a third time
rather than promoted, per the "a helper is promoted only once a *second
module* calls it" rule not applying across test files each owned by a
different sprint).

Every scenario mints its own `turn_id` per real action -- `take`, `give`
and `use_item` each spend a creature's action for the turn (08a's rule,
reused unchanged), so a scenario doing two of them needs two turns. `drop`
spends nothing: AC2 below takes then drops inside a single turn on
purpose, since that only succeeds if `drop` really is free -- if it spent
the turn's action instead, the `drop` right after `take` would itself
raise `ALREADY_ACTED`.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
in a scenario is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against `take`/
`drop`/`give`/`use_item` or `.errors` themselves -- this suite is red until
they land, and green once they do.
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

ENTRY_SCENE = "village-green"
TO_THORNWAY = "to-thornway"  # village-green -> thornway
TO_LAIR_MAW = "to-lair-maw"  # thornway -> lair-maw
TO_LAIR_HOLLOW = "to-lair-hollow"  # lair-maw -> lair-hollow

HORSESHOE_TEMPLATE = "bent-horseshoe"  # loose on the ground, village-green
MIRA_TEMPLATE = "mira"  # creature, village-green
KNIFE_TEMPLATE = "shepherds-knife"  # both Mira's and the seed character's own
WOOL_SACK_TEMPLATE = "wool-sack"  # fixture, lair-hollow
FLEECE_TEMPLATE = "stolen-fleece"  # x2, carried by the wool sack
GOBLIN_BOSS_TEMPLATE = "goblin-boss"  # creature, lair-hollow
CLEAVER_TEMPLATE = "notched-cleaver"  # carried by the goblin boss


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _second_connection:
    """An `AsyncSession` on its own connection to the same scratch
    database `playthrough_db` already pinned `DATABASE_URL` to -- never a
    session a call under test itself ran on. The only way to read what is
    genuinely committed rather than merely flushed and still pending in
    the other session's open transaction."""

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


async def _dm_tool_calls(session, run_id: str, *, result: str, name: str) -> list[dict]:
    """`tool_call` events at `dm` visibility, filtered to `result` and
    `name` -- a run also carries `use_exit`'s own `tool_call` events (the
    walk between scenes), which must never be mistaken for a mover's."""
    rows = (
        await session.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' AND visibility = 'dm' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [
        p
        for p in (_payload(row) for row in rows)
        if p.get("result") == result and p.get("name") == name
    ]


async def _object_id_by_template(session, run_id: str, template_id: str) -> str:
    row = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id"
            ),
            {"run_id": run_id, "template_id": template_id},
        )
    ).one()
    return row.id


async def _carried_object_ids(session, *, owner_id: str, template_id: str) -> list[str]:
    """Every object id `owner_id` carries with `template_id`, ordered for
    determinism -- the wool sack carries two `stolen-fleece` rows, every
    other carrier in this file carries exactly one of its own template."""
    rows = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE owner_object_id = :owner_id "
                "AND template_id = :template_id ORDER BY id"
            ),
            {"owner_id": owner_id, "template_id": template_id},
        )
    ).all()
    return [row.id for row in rows]


async def _object_position(session, object_id: str) -> tuple:
    """`(owner_object_id, adventure_run_id, scene_id)` for one object --
    what every mover under test either sets, clears or must leave alone on
    a refusal."""
    row = (
        await session.execute(
            text("SELECT owner_object_id, adventure_run_id, scene_id FROM objects WHERE id = :id"),
            {"id": object_id},
        )
    ).one()
    return (row.owner_object_id, row.adventure_run_id, row.scene_id)


async def _objects_snapshot(session, run_id: str) -> list[tuple]:
    """Every `objects` row belonging to `run_id`, every column a mover
    could plausibly write -- not just the one item a scenario names -- so
    "nothing moves" is checked against the whole world, not one row picked
    in advance."""
    rows = (
        await session.execute(
            text(
                "SELECT id, kind, template_id, name, member_id, owner_object_id, "
                "adventure_run_id, scene_id, current_hp, max_hp, armour_class, "
                "is_alive, state FROM objects WHERE campaign_run_id = :run_id ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [tuple(row) for row in rows]


async def _enter_village_green(playthrough_db, *, username: str):
    """Shared opening for every scenario below: a fresh user, campaign run
    and character, dropped into `village-green`. Returns `(owner_id, run,
    character)`."""
    owner_id = generate_id()
    await _insert_user(playthrough_db, owner_id, username=username)
    await playthrough_db.commit()

    run = await playthrough_service.start_campaign_run(
        playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
    )
    character = await playthrough_service.create_character(
        playthrough_db, user_id=owner_id, run_id=run.id
    )
    await playthrough_service.enter_adventure(playthrough_db, user_id=owner_id, run_id=run.id)
    return owner_id, run, character


async def _walk_to_lair_hollow(playthrough_db, *, user_id: str, actor_id: str) -> None:
    # `use_exit` takes no `turn_id` at all yet -- every use lands free,
    # regardless of any turn a scenario is otherwise tracking.
    await playthrough_service.use_exit(
        playthrough_db, user_id=user_id, actor_id=actor_id, exit_id=TO_THORNWAY
    )
    await playthrough_service.use_exit(
        playthrough_db, user_id=user_id, actor_id=actor_id, exit_id=TO_LAIR_MAW
    )
    await playthrough_service.use_exit(
        playthrough_db, user_id=user_id, actor_id=actor_id, exit_id=TO_LAIR_HOLLOW
    )


@pytest.mark.database
def test_ac2_take_drop_and_give_move_the_item_and_refuse_across_scenes_or_another_creatures_hands(
    playthrough_db,
):
    # <- AC2
    async def _scenario():
        owner_id, run, character = await _enter_village_green(playthrough_db, username="ac2-owner")

        horseshoe_id = await _object_id_by_template(playthrough_db, run.id, HORSESHOE_TEMPLATE)
        mira_id = await _object_id_by_template(playthrough_db, run.id, MIRA_TEMPLATE)
        (mira_knife_id,) = await _carried_object_ids(
            playthrough_db, owner_id=mira_id, template_id=KNIFE_TEMPLATE
        )
        (actor_knife_id,) = await _carried_object_ids(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )

        # -- take puts the horseshoe in the actor's hands and off the
        # floor; a free drop right after, in the very same turn, puts it
        # straight back -- proving `drop` spends no action, since `take`
        # already spent this turn's.
        take_drop_turn = generate_id()
        take_result = await playthrough_service.take(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=take_drop_turn,
        )
        assert take_result is None
        assert await _object_position(playthrough_db, horseshoe_id) == (character.id, None, None)

        take_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok", name="take")
        assert len(take_calls) == 1
        assert take_calls[0]["args"] == {"actorId": str(character.id), "itemId": str(horseshoe_id)}
        assert take_calls[0]["outcome"] == {}

        drop_result = await playthrough_service.drop(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=take_drop_turn,
        )
        assert drop_result is None
        after_drop = await _object_position(playthrough_db, horseshoe_id)
        assert after_drop[0] is None
        assert after_drop[2] == ENTRY_SCENE
        actor_adventure_run_id = (await _object_position(playthrough_db, character.id))[1]
        assert after_drop[1] == actor_adventure_run_id

        drop_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok", name="drop")
        assert len(drop_calls) == 1
        assert drop_calls[0]["args"] == {"actorId": str(character.id), "itemId": str(horseshoe_id)}
        assert drop_calls[0]["outcome"] == {}

        # -- refusal: an item held by another creature cannot be taken,
        # even from the actor's own scene -- the widening is for
        # containers only, never for pickpocketing a creature.
        pickpocket_turn = generate_id()
        before_knife = await _object_position(playthrough_db, mira_knife_id)
        with pytest.raises(Exception) as held_by_other:
            await playthrough_service.take(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                item_id=mira_knife_id,
                turn_id=pickpocket_turn,
            )
        assert held_by_other.value.code == ErrorCode.OBJECT_NOT_REACHABLE
        assert await _object_position(playthrough_db, mira_knife_id) == before_knife

        async with _second_connection() as reader:
            refused_take = await _dm_tool_calls(reader, run.id, result="refused", name="take")
            assert len(refused_take) == 1
            assert refused_take[0]["args"] == {
                "actorId": str(character.id),
                "itemId": str(mira_knife_id),
            }

        # -- give: the actor re-takes the horseshoe (a fresh action) and
        # hands it to Mira -- one creature to another.
        retake_turn = generate_id()
        await playthrough_service.take(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=retake_turn,
        )

        give_turn = generate_id()
        give_result = await playthrough_service.give(
            playthrough_db,
            user_id=owner_id,
            from_id=character.id,
            to_id=mira_id,
            item_id=horseshoe_id,
            turn_id=give_turn,
        )
        assert give_result is None
        assert await _object_position(playthrough_db, horseshoe_id) == (mira_id, None, None)

        give_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok", name="give")
        assert len(give_calls) == 1
        assert give_calls[0]["args"] == {
            "actorId": str(character.id),
            "toId": str(mira_id),
            "itemId": str(horseshoe_id),
        }
        assert give_calls[0]["outcome"] == {}

        # -- refusal: any of the three across two different scenes -- the
        # actor leaves the green; Mira stays behind.
        await playthrough_service.use_exit(
            playthrough_db, user_id=owner_id, actor_id=character.id, exit_id=TO_THORNWAY
        )

        cross_scene_turn = generate_id()
        before_actor_knife = await _object_position(playthrough_db, actor_knife_id)
        with pytest.raises(Exception) as cross_scene:
            await playthrough_service.give(
                playthrough_db,
                user_id=owner_id,
                from_id=character.id,
                to_id=mira_id,
                item_id=actor_knife_id,
                turn_id=cross_scene_turn,
            )
        assert cross_scene.value.code == ErrorCode.OBJECT_NOT_REACHABLE
        assert await _object_position(playthrough_db, actor_knife_id) == before_actor_knife

        async with _second_connection() as reader:
            refused_give = await _dm_tool_calls(reader, run.id, result="refused", name="give")
            assert len(refused_give) == 1
            assert refused_give[0]["args"] == {
                "actorId": str(character.id),
                "toId": str(mira_id),
                "itemId": str(actor_knife_id),
            }

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac5_a_container_in_the_scene_is_looted_but_a_creatures_own_hands_are_not(playthrough_db):
    # <- AC5
    async def _scenario():
        owner_id, run, character = await _enter_village_green(playthrough_db, username="ac5-owner")
        await _walk_to_lair_hollow(playthrough_db, user_id=owner_id, actor_id=character.id)

        wool_sack_id = await _object_id_by_template(playthrough_db, run.id, WOOL_SACK_TEMPLATE)
        fleece_ids = await _carried_object_ids(
            playthrough_db, owner_id=wool_sack_id, template_id=FLEECE_TEMPLATE
        )
        assert len(fleece_ids) == 2
        fleece_id = fleece_ids[0]

        goblin_boss_id = await _object_id_by_template(playthrough_db, run.id, GOBLIN_BOSS_TEMPLATE)
        (cleaver_id,) = await _carried_object_ids(
            playthrough_db, owner_id=goblin_boss_id, template_id=CLEAVER_TEMPLATE
        )

        # -- the sack is a non-creature object standing in the actor's own
        # scene: a fleeces it carries can be taken straight out of it.
        loot_turn = generate_id()
        loot_result = await playthrough_service.take(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            item_id=fleece_id,
            turn_id=loot_turn,
        )
        assert loot_result is None
        assert await _object_position(playthrough_db, fleece_id) == (character.id, None, None)

        loot_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok", name="take")
        assert len(loot_calls) == 1
        assert loot_calls[0]["args"] == {"actorId": str(character.id), "itemId": str(fleece_id)}

        # -- refusal: the goblin boss's own cleaver, held in the same
        # scene, is a creature's hands, not a container -- still refused.
        pickpocket_turn = generate_id()
        before_cleaver = await _object_position(playthrough_db, cleaver_id)
        with pytest.raises(Exception) as pickpocket:
            await playthrough_service.take(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                item_id=cleaver_id,
                turn_id=pickpocket_turn,
            )
        assert pickpocket.value.code == ErrorCode.OBJECT_NOT_REACHABLE
        assert await _object_position(playthrough_db, cleaver_id) == before_cleaver

        async with _second_connection() as reader:
            refused = await _dm_tool_calls(reader, run.id, result="refused", name="take")
            assert len(refused) == 1
            assert refused[0]["args"] == {"actorId": str(character.id), "itemId": str(cleaver_id)}

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_use_item_refuses_every_template_as_not_consumable_and_nothing_moves(playthrough_db):
    # <- AC4
    async def _scenario():
        owner_id, run, character = await _enter_village_green(playthrough_db, username="ac4-owner")

        horseshoe_id = await _object_id_by_template(playthrough_db, run.id, HORSESHOE_TEMPLATE)
        (actor_knife_id,) = await _carried_object_ids(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )

        # Two different templates, one carried and one not -- "whatever the
        # item" is genuinely whatever, not one item this suite happens to
        # have picked.
        for item_id in (actor_knife_id, horseshoe_id):
            turn_id = generate_id()
            before = await _objects_snapshot(playthrough_db, run.id)
            with pytest.raises(Exception) as not_consumable:
                await playthrough_service.use_item(
                    playthrough_db,
                    user_id=owner_id,
                    actor_id=character.id,
                    item_id=item_id,
                    turn_id=turn_id,
                )
            assert not_consumable.value.code == ErrorCode.ITEM_NOT_CONSUMABLE
            after = await _objects_snapshot(playthrough_db, run.id)
            assert after == before

        async with _second_connection() as reader:
            refused = await _dm_tool_calls(reader, run.id, result="refused", name="use_item")
            assert len(refused) == 2
            assert {c["args"].get("itemId") for c in refused} == {
                str(actor_knife_id),
                str(horseshoe_id),
            }
            for call in refused:
                assert call["args"].get("actorId") == str(character.id)

    asyncio.run(_scenario())
