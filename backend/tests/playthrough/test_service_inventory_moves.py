"""WI1 (sprint 08b): items moving between the floor, a pack and a
container -- `take`, `drop`, `give` -- plus the `use_item` seam that
refuses everything (AC2, AC4, AC5).

qa's own `test_acceptance_inventory_moves.py` drives the black-box happy
path and refusals against the sprint's interface contracts; this file
covers the reachability rule each mechanic weighs on its own row (an item
in another scene, one carried by another creature, an actor standing
nowhere, AC5's widening onto a non-creature container), the gate order
shared with `interact`/08a's one-action rule, and `use_item`'s
unconditional refusal.

`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content, walking
the same path `test_service_interact.py` and qa's own suite do:
`village-green` -> `thornway` -> `lair-maw` -> `lair-hollow`, where
`wool-sack` and Grettle (`goblin-boss`) stand.

No `pytest-asyncio` (AGENTS.md gotchas): every async call in one scenario
is wrapped in a single `asyncio.run(...)`.
"""

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.playthrough import service
from app.modules.playthrough.errors import (
    AlreadyActedError,
    GameObjectNotFoundError,
    ItemNotConsumableError,
    ObjectNotReachableError,
)

CAMPAIGN_ID = "greenhollow"


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _second_connection:
    """An independent connection to the same scratch database, opened only
    after a refusing call has already raised -- proves the refusal is
    genuinely committed rather than merely flushed into the writer's own
    still-open transaction (same helper `test_service_interact.py` and
    `test_service_one_action_per_turn.py` each keep their own copy of)."""

    async def __aenter__(self):
        self._engine = create_async_engine(os.environ["DATABASE_URL"])
        sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._session = sessionmaker()
        return self._session

    async def __aexit__(self, *exc_info) -> None:
        await self._session.close()
        await self._engine.dispose()


async def _new_run(db: AsyncSession, *, username: str):
    """A fresh run and its one character, not yet in any adventure --
    `character.scene_id` is `None`."""
    user_id = generate_id()
    await _insert_user(db, user_id, username=username)
    await db.commit()

    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id)
    return user_id, run, character


async def _reach_village_green(db: AsyncSession, *, username: str):
    """A fresh run, positioned at `village-green` -- the adventure's own
    entry scene, reached with no `use_exit` call at all."""
    user_id, run, character = await _new_run(db, username=username)
    await service.enter_adventure(db, user_id=user_id, run_id=run.id)
    return user_id, run, character


async def _reach_lair_maw(db: AsyncSession, *, username: str):
    user_id, run, character = await _reach_village_green(db, username=username)
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-thornway")
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-lair-maw")
    return user_id, run, character


async def _reach_lair_hollow(db: AsyncSession, *, username: str):
    user_id, run, character = await _reach_lair_maw(db, username=username)
    await service.use_exit(db, user_id=user_id, actor_id=character.id, exit_id="to-lair-hollow")
    return user_id, run, character


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


async def _object_row(db: AsyncSession, object_id: str):
    return (
        await db.execute(
            text("SELECT owner_object_id, adventure_run_id, scene_id FROM objects WHERE id = :id"),
            {"id": object_id},
        )
    ).one()


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


# --- take -----------------------------------------------------------------


@pytest.mark.database
def test_take_sets_owner_and_clears_position_for_an_item_in_the_actors_scene(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="take-scene-item"
        )
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        turn_id = generate_id()

        result = await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=turn_id,
        )
        assert result is None

        row = await _object_row(playthrough_db, horseshoe_id)
        assert row.owner_object_id == character.id
        assert row.adventure_run_id is None
        assert row.scene_id is None

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="take")
        assert len(ok_calls) == 1
        assert ok_calls[0]["args"] == {"actorId": character.id, "itemId": horseshoe_id}
        assert ok_calls[0]["rollIds"] == []
        assert ok_calls[0]["outcome"] == {}

    asyncio.run(_scenario())


@pytest.mark.database
def test_take_refuses_an_item_in_another_scene(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="take-far-scene")
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        before = await _object_row(playthrough_db, horseshoe_id)

        with pytest.raises(ObjectNotReachableError) as excinfo:
            await service.take(
                playthrough_db, user_id=user_id, actor_id=character.id, item_id=horseshoe_id
            )
        assert excinfo.value.code == ErrorCode.OBJECT_NOT_REACHABLE

        after = await _object_row(playthrough_db, horseshoe_id)
        assert after == before

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="take")
            assert len(refused) == 1
            assert refused[0]["args"] == {"actorId": character.id, "itemId": horseshoe_id}
            assert "reason" in refused[0]["outcome"]

    asyncio.run(_scenario())


@pytest.mark.database
def test_take_refuses_an_item_held_by_another_creature(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_hollow(
            playthrough_db, username="take-held-by-creature"
        )
        cleaver_id = await _object_id(playthrough_db, run_id=run.id, template_id="notched-cleaver")

        with pytest.raises(ObjectNotReachableError) as excinfo:
            await service.take(
                playthrough_db, user_id=user_id, actor_id=character.id, item_id=cleaver_id
            )
        assert excinfo.value.code == ErrorCode.OBJECT_NOT_REACHABLE

        row = await _object_row(playthrough_db, cleaver_id)
        assert row.owner_object_id != character.id

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="take")
            assert len(refused) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_take_accepts_an_item_whose_owner_is_a_non_creature_object_in_the_actors_scene(
    playthrough_db,
):
    """AC5: `stolen-fleece` is owned by `wool-sack`, a fixture standing in
    the actor's own scene -- the widening this sprint makes."""

    async def _scenario():
        user_id, run, character = await _reach_lair_hollow(
            playthrough_db, username="take-from-container"
        )
        fleece_id = await _object_id(playthrough_db, run_id=run.id, template_id="stolen-fleece")

        await service.take(
            playthrough_db, user_id=user_id, actor_id=character.id, item_id=fleece_id
        )

        row = await _object_row(playthrough_db, fleece_id)
        assert row.owner_object_id == character.id
        assert row.adventure_run_id is None
        assert row.scene_id is None

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="take")
        assert len(ok_calls) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_take_refuses_when_the_actor_has_no_current_scene(playthrough_db):
    """Before `enter_adventure`, both the actor and every seeded item share
    `scene_id = None` -- proves the actor's own position is checked first,
    rather than two `None`s comparing accidentally equal."""

    async def _scenario():
        user_id, run, character = await _new_run(playthrough_db, username="take-no-scene")
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        assert character.scene_id is None

        with pytest.raises(ObjectNotReachableError):
            await service.take(
                playthrough_db, user_id=user_id, actor_id=character.id, item_id=horseshoe_id
            )

        row = await _object_row(playthrough_db, horseshoe_id)
        assert row.owner_object_id is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_take_raises_not_found_for_an_item_on_a_foreign_run(playthrough_db):
    async def _scenario():
        user_id_a, run_a, character_a = await _reach_village_green(
            playthrough_db, username="take-foreign-a"
        )
        _user_id_b, run_b, _character_b = await _reach_village_green(
            playthrough_db, username="take-foreign-b"
        )
        horseshoe_b = await _object_id(
            playthrough_db, run_id=run_b.id, template_id="bent-horseshoe"
        )

        with pytest.raises(GameObjectNotFoundError):
            await service.take(
                playthrough_db, user_id=user_id_a, actor_id=character_a.id, item_id=horseshoe_b
            )

    asyncio.run(_scenario())


@pytest.mark.database
def test_take_then_give_in_the_same_turn_is_refused_as_already_acted(playthrough_db):
    """`take` and `give` both spend the turn's action -- proves the
    one-action gate 08a built is applied here, unchanged."""

    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="take-give-one-turn"
        )
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        mira_id = await _object_id(playthrough_db, run_id=run.id, template_id="mira")
        turn_id = generate_id()

        await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=turn_id,
        )

        with pytest.raises(AlreadyActedError) as excinfo:
            await service.give(
                playthrough_db,
                user_id=user_id,
                from_id=character.id,
                to_id=mira_id,
                item_id=horseshoe_id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.ALREADY_ACTED

        row = await _object_row(playthrough_db, horseshoe_id)
        assert row.owner_object_id == character.id  # the refused give moved nothing

    asyncio.run(_scenario())


@pytest.mark.database
def test_take_refuses_a_second_take_in_the_same_turn(playthrough_db):
    """`take`'s own gate, not just a later mechanic's: a second reachable
    item in the same turn is refused by `take` itself."""

    async def _scenario():
        user_id, run, character = await _reach_lair_hollow(
            playthrough_db, username="take-second-take"
        )
        fleece_rows = (
            (
                await playthrough_db.execute(
                    text(
                        "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                        "AND template_id = 'stolen-fleece' ORDER BY id"
                    ),
                    {"run_id": run.id},
                )
            )
            .scalars()
            .all()
        )
        assert len(fleece_rows) == 2
        first_fleece, second_fleece = fleece_rows
        turn_id = generate_id()

        await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=first_fleece,
            turn_id=turn_id,
        )

        with pytest.raises(AlreadyActedError) as excinfo:
            await service.take(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                item_id=second_fleece,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.ALREADY_ACTED

        row = await _object_row(playthrough_db, second_fleece)
        # Still owned by `wool-sack`, its original container -- the refused
        # take never touched it (stolen-fleece is carried, never `None`).
        assert row.owner_object_id != character.id

    asyncio.run(_scenario())


# --- give -------------------------------------------------------------------


@pytest.mark.database
def test_give_reowns_the_item_between_two_creatures_in_one_scene(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="give-happy-path"
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

        result = await service.give(
            playthrough_db,
            user_id=user_id,
            from_id=character.id,
            to_id=mira_id,
            item_id=horseshoe_id,
            turn_id=generate_id(),
        )
        assert result is None

        row = await _object_row(playthrough_db, horseshoe_id)
        assert row.owner_object_id == mira_id
        assert row.adventure_run_id is None
        assert row.scene_id is None

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="give")
        assert len(ok_calls) == 1
        assert ok_calls[0]["args"] == {
            "actorId": character.id,
            "toId": mira_id,
            "itemId": horseshoe_id,
        }
        assert ok_calls[0]["outcome"] == {}

    asyncio.run(_scenario())


@pytest.mark.database
def test_give_refuses_when_the_receiver_is_in_another_scene(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="give-far-receiver"
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
        # Mira stays behind on the green; the character walks on alone.
        await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id="to-thornway"
        )
        await service.use_exit(
            playthrough_db, user_id=user_id, actor_id=character.id, exit_id="to-lair-maw"
        )

        with pytest.raises(ObjectNotReachableError) as excinfo:
            await service.give(
                playthrough_db,
                user_id=user_id,
                from_id=character.id,
                to_id=mira_id,
                item_id=horseshoe_id,
                turn_id=generate_id(),
            )
        assert excinfo.value.code == ErrorCode.OBJECT_NOT_REACHABLE

        row = await _object_row(playthrough_db, horseshoe_id)
        assert row.owner_object_id == character.id

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="give")
            assert len(refused) == 1
            assert refused[0]["args"] == {
                "actorId": character.id,
                "toId": mira_id,
                "itemId": horseshoe_id,
            }

    asyncio.run(_scenario())


@pytest.mark.database
def test_give_refuses_when_the_giver_does_not_carry_the_item(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="give-not-carried"
        )
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        mira_id = await _object_id(playthrough_db, run_id=run.id, template_id="mira")

        with pytest.raises(ObjectNotReachableError):
            await service.give(
                playthrough_db,
                user_id=user_id,
                from_id=character.id,
                to_id=mira_id,
                item_id=horseshoe_id,
                turn_id=generate_id(),
            )

        row = await _object_row(playthrough_db, horseshoe_id)
        assert row.owner_object_id is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_give_refuses_when_the_receiver_is_not_a_creature(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_hollow(
            playthrough_db, username="give-not-a-creature"
        )
        fleece_id = await _object_id(playthrough_db, run_id=run.id, template_id="stolen-fleece")
        wool_sack_id = await _object_id(playthrough_db, run_id=run.id, template_id="wool-sack")

        await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=fleece_id,
            turn_id=generate_id(),
        )

        with pytest.raises(ObjectNotReachableError):
            await service.give(
                playthrough_db,
                user_id=user_id,
                from_id=character.id,
                to_id=wool_sack_id,
                item_id=fleece_id,
                turn_id=generate_id(),
            )

        row = await _object_row(playthrough_db, fleece_id)
        assert row.owner_object_id == character.id

    asyncio.run(_scenario())


# --- drop -------------------------------------------------------------------


@pytest.mark.database
def test_take_then_drop_in_the_same_turn_succeeds_because_dropping_is_free(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_hollow(playthrough_db, username="drop-is-free")
        fleece_id = await _object_id(playthrough_db, run_id=run.id, template_id="stolen-fleece")
        turn_id = generate_id()

        await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=fleece_id,
            turn_id=turn_id,
        )

        # If `drop` spent the turn's action too, this would raise
        # `AlreadyActedError` instead of succeeding.
        result = await service.drop(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=fleece_id,
            turn_id=turn_id,
        )
        assert result is None

        row = await _object_row(playthrough_db, fleece_id)
        assert row.owner_object_id is None
        assert row.adventure_run_id == character.adventure_run_id
        assert row.scene_id == character.scene_id

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="drop")
        assert len(ok_calls) == 1
        assert ok_calls[0]["args"] == {"actorId": character.id, "itemId": fleece_id}
        assert ok_calls[0]["outcome"] == {}

    asyncio.run(_scenario())


@pytest.mark.database
def test_drop_refuses_an_item_not_carried_by_the_actor(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_lair_hollow(
            playthrough_db, username="drop-not-carried"
        )
        cleaver_id = await _object_id(playthrough_db, run_id=run.id, template_id="notched-cleaver")

        with pytest.raises(ObjectNotReachableError) as excinfo:
            await service.drop(
                playthrough_db, user_id=user_id, actor_id=character.id, item_id=cleaver_id
            )
        assert excinfo.value.code == ErrorCode.OBJECT_NOT_REACHABLE

        row = await _object_row(playthrough_db, cleaver_id)
        assert row.owner_object_id != character.id

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="drop")
            assert len(refused) == 1

    asyncio.run(_scenario())


# --- use_item -----------------------------------------------------------


@pytest.mark.database
def test_use_item_refuses_every_item_as_not_consumable(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="use-item-refused"
        )
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id="shepherds-knife"
        )

        with pytest.raises(ItemNotConsumableError) as excinfo:
            await service.use_item(
                playthrough_db, user_id=user_id, actor_id=character.id, item_id=knife_id
            )
        assert excinfo.value.code == ErrorCode.ITEM_NOT_CONSUMABLE

        row = await _object_row(playthrough_db, knife_id)
        assert row.owner_object_id == character.id  # untouched

        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, result="refused", name="use_item")
            assert len(refused) == 1
            assert refused[0]["args"] == {"actorId": character.id, "itemId": knife_id}

        ok_calls = await _tool_calls(playthrough_db, run.id, result="ok", name="use_item")
        assert ok_calls == []

    asyncio.run(_scenario())


@pytest.mark.database
def test_use_item_checks_already_acted_before_the_consumable_refusal(playthrough_db):
    async def _scenario():
        user_id, run, character = await _reach_village_green(
            playthrough_db, username="use-item-already-acted"
        )
        horseshoe_id = await _object_id(playthrough_db, run_id=run.id, template_id="bent-horseshoe")
        knife_id = await _owned_object_id(
            playthrough_db, owner_id=character.id, template_id="shepherds-knife"
        )
        turn_id = generate_id()

        await service.take(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            item_id=horseshoe_id,
            turn_id=turn_id,
        )

        with pytest.raises(AlreadyActedError) as excinfo:
            await service.use_item(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                item_id=knife_id,
                turn_id=turn_id,
            )
        assert excinfo.value.code == ErrorCode.ALREADY_ACTED

        refused = await _tool_calls(playthrough_db, run.id, result="refused", name="use_item")
        assert len(refused) == 1

    asyncio.run(_scenario())
