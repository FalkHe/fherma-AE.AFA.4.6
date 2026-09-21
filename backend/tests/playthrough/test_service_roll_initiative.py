"""WI2 (sprint 09): rolling to see who goes first -- `roll_initiative`
(AC4) -- and the negative claim the whole sprint stands on: nothing
anywhere records that a fight is happening.

qa's own `test_acceptance_fight_in_the_transcript.py` drives the black-box
happy path (two sides, one holding the character, one holding the
goblins) against the sprint's interface contract; this file covers
`roll_initiative`'s own composition rules -- which id in a side is asked
versus rolled outright, that a side is scanned rather than assumed to put
its member first, that no row and no `tool_call` are ever written -- and
carries its own copy of AC4's schema-wide negative assertion so this work
item's own suite, not only qa's, would catch a mechanic that started
quietly recording a fight.

`@pytest.mark.database`, against the shared scratch-database fixture
(`playthrough_db`) and the real shipped `greenhollow/v1` content: the seed
character (Dexterity 12, modifier +1) and the `goblin` (Dexterity 14,
modifier +2) placed in `lair-maw`, reached the same way
`test_service_attack_and_damage.py` and qa's own suite do: `village-green`
-> `thornway` -> `lair-maw`.

No `pytest-asyncio` (`AGENTS.md` gotchas): every async call in one
scenario is wrapped in a single `asyncio.run(...)`.
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
KNIFE_TEMPLATE = "shepherds-knife"

CHARACTER_DEX_MODIFIER = 1
GOBLIN_DEX_MODIFIER = 2

# The public schema's tables and the two tables' own columns -- fixed by
# migrations `0001`-`0007`; this sprint adds none of either. The copy in
# qa's own acceptance file is the authoritative one -- kept identical here
# on purpose, so a drift between the two would itself be a signal.
EXPECTED_TABLES = {
    "users",
    "sessions",
    "srd_rules",
    "campaign_runs",
    "campaign_run_members",
    "adventure_runs",
    "objects",
    "events",
    "alembic_version",
}
EXPECTED_OBJECTS_COLUMNS = {
    "id",
    "campaign_run_id",
    "member_id",
    "kind",
    "template_id",
    "instance_key",
    "name",
    "source_adventure_id",
    "source_scene_id",
    "adventure_run_id",
    "scene_id",
    "owner_object_id",
    "current_hp",
    "max_hp",
    "armour_class",
    "is_alive",
    "state",
    "created_at",
    "updated_at",
}
EXPECTED_EVENTS_COLUMNS = {
    "id",
    "campaign_run_id",
    "actor_member_id",
    "turn_id",
    "type",
    "visibility",
    "payload",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
    "created_at",
}


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call -- the same seam
    and subclass every other acceptance/service suite in this module
    uses, so a roll's `total` is a known number rather than a real one."""

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


async def _carried_object_id(db: AsyncSession, *, owner_id: str, template_id: str) -> str:
    return (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE owner_object_id = :owner_id "
                "AND template_id = :template_id LIMIT 1"
            ),
            {"owner_id": owner_id, "template_id": template_id},
        )
    ).scalar_one()


async def _events_row(db: AsyncSession, event_id: str):
    return (
        await db.execute(
            text("SELECT type, visibility, turn_id, payload FROM events WHERE id = :id"),
            {"id": event_id},
        )
    ).one()


async def _tool_call_count(db: AsyncSession, run_id: str) -> int:
    return (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call'"
            ),
            {"run_id": run_id},
        )
    ).scalar_one()


async def _objects_snapshot(db: AsyncSession, run_id: str) -> list[tuple]:
    rows = (
        await db.execute(
            text(
                "SELECT id, kind, template_id, name, member_id, owner_object_id, "
                "adventure_run_id, scene_id, current_hp, max_hp, armour_class, "
                "is_alive, state FROM objects WHERE campaign_run_id = :run_id ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [tuple(row) for row in rows]


async def _table_names(db: AsyncSession) -> set[str]:
    rows = (
        await db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
        )
    ).all()
    return {row.table_name for row in rows}


async def _column_names(db: AsyncSession, table: str) -> set[str]:
    rows = (
        await db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table"
            ),
            {"table": table},
        )
    ).all()
    return {row.column_name for row in rows}


async def _state_keys(db: AsyncSession, run_id: str) -> set[str]:
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT jsonb_object_keys(state) AS key FROM objects "
                "WHERE campaign_run_id = :run_id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return {row.key for row in rows}


@pytest.mark.database
def test_a_side_with_the_character_is_asked_a_side_without_is_rolled_outright(playthrough_db):
    # <- AC4
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="ri-owner")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)
        turn = generate_id()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([15]))
            event_a, event_b = await service.roll_initiative(
                playthrough_db,
                user_id=user_id,
                side_a_ids=[character.id],
                side_b_ids=goblin_ids,
                turn_id=turn,
            )

        # -- side_a carries the character: it is *asked*, not rolled for.
        assert event_a.type == "roll_requested"
        row_a = await _events_row(playthrough_db, event_a.id)
        assert row_a.visibility == "player"
        assert row_a.turn_id == turn
        assert row_a.payload["kind"] == "initiative"
        assert row_a.payload["actorId"] == str(character.id)
        assert row_a.payload["formula"] == f"1d20+{CHARACTER_DEX_MODIFIER}"

        # -- side_b holds only goblins, none a member's own: rolled
        # outright, at `player` visibility, on the first id of the side.
        assert event_b.type == "roll"
        row_b = await _events_row(playthrough_db, event_b.id)
        assert row_b.visibility == "player"
        assert row_b.turn_id == turn
        assert row_b.payload["kind"] == "initiative"
        assert row_b.payload["actorId"] == str(goblin_ids[0])
        assert row_b.payload["formula"] == f"1d20+{GOBLIN_DEX_MODIFIER}"
        assert row_b.payload["total"] == 15 + GOBLIN_DEX_MODIFIER

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_member_later_in_the_side_list_is_still_found(playthrough_db):
    # A side is scanned for its member, not assumed to carry one first.
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="ri-scan")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([10]))
            event_a, _event_b = await service.roll_initiative(
                playthrough_db,
                user_id=user_id,
                side_a_ids=[goblin_ids[0], goblin_ids[1], character.id],
                side_b_ids=[goblin_ids[2]],
            )

        assert event_a.type == "roll_requested"
        row_a = await _events_row(playthrough_db, event_a.id)
        assert row_a.payload["actorId"] == str(character.id)

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_side_with_no_member_uses_its_first_id_as_the_side_s_roll(playthrough_db):
    async def _scenario():
        user_id, run, _character = await _reach_lair_maw(playthrough_db, username="ri-noone")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([8, 8]))
            event_a, event_b = await service.roll_initiative(
                playthrough_db,
                user_id=user_id,
                side_a_ids=[goblin_ids[1], goblin_ids[0]],
                side_b_ids=[goblin_ids[2]],
            )

        row_a = await _events_row(playthrough_db, event_a.id)
        assert row_a.payload["actorId"] == str(goblin_ids[1])
        row_b = await _events_row(playthrough_db, event_b.id)
        assert row_b.payload["actorId"] == str(goblin_ids[2])

    asyncio.run(_scenario())


@pytest.mark.database
def test_writes_exactly_two_roll_events_and_no_object_row_and_no_tool_call(playthrough_db):
    # <- AC4
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="ri-inert")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)

        before = await _objects_snapshot(playthrough_db, run.id)
        before_event_count = (
            await playthrough_db.execute(
                text("SELECT COUNT(*) FROM events WHERE campaign_run_id = :run_id"),
                {"run_id": run.id},
            )
        ).scalar_one()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([12]))
            event_a, _event_b = await service.roll_initiative(
                playthrough_db,
                user_id=user_id,
                side_a_ids=[character.id],
                side_b_ids=goblin_ids,
            )

        # -- Not one `objects` row anywhere in the run changed.
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        # -- No `tool_call` was ever written -- finding out who goes first
        # spends nobody's turn.
        assert await _tool_call_count(playthrough_db, run.id) == 0

        # -- Exactly two new events, the `roll_requested` and its `roll`
        # events -- side_a's own request is still open at this point.
        after_event_count = (
            await playthrough_db.execute(
                text("SELECT COUNT(*) FROM events WHERE campaign_run_id = :run_id"),
                {"run_id": run.id},
            )
        ).scalar_one()
        assert after_event_count - before_event_count == 2

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([9]))
            await service.resolve_roll_request(
                playthrough_db, user_id=user_id, request_id=event_a.id
            )

        rolls = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'roll' AND payload->>'kind' = 'initiative'"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(rolls) == 2

    asyncio.run(_scenario())


@pytest.mark.database
def test_no_fight_state_survives_initiative_and_a_landed_attack(playthrough_db):
    # <- AC4, the negative claim: exact sets, not a blacklist.
    async def _scenario():
        user_id, run, character = await _reach_lair_maw(playthrough_db, username="ri-noleak")
        goblin_ids = await _goblin_ids(playthrough_db, run_id=run.id)
        knife_id = await _carried_object_id(
            playthrough_db, owner_id=character.id, template_id=KNIFE_TEMPLATE
        )

        assert await _table_names(playthrough_db) == EXPECTED_TABLES
        assert await _column_names(playthrough_db, "objects") == EXPECTED_OBJECTS_COLUMNS
        assert await _column_names(playthrough_db, "events") == EXPECTED_EVENTS_COLUMNS
        state_keys_before = await _state_keys(playthrough_db, run.id)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([15]))
            _event_a, event_b = await service.roll_initiative(
                playthrough_db,
                user_id=user_id,
                side_a_ids=[character.id],
                side_b_ids=goblin_ids,
            )
        assert event_b.type == "roll"  # side_b resolved outright already

        # -- A whole (short) fight on top of the initiative rolls: a hit
        # and the wound it causes -- if any mechanic here quietly wrote
        # combat state, it would exist by the time the assertion below
        # looks for it.
        turn = generate_id()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([9]))
            attack_roll = await service.roll(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                kind="attack",
                context={"item_id": KNIFE_TEMPLATE},
                turn_id=turn,
            )
        await service.attack(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            target_id=goblin_ids[0],
            item_id=knife_id,
            roll_id=attack_roll.id,
            turn_id=turn,
        )
        hit_id = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call' AND payload->>'name' = 'attack' "
                    "AND payload->>'result' = 'ok'"
                ),
                {"run_id": run.id},
            )
        ).scalar_one()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([4]))
            damage_roll = await service.roll(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                kind="damage",
                context={"item_id": KNIFE_TEMPLATE},
                turn_id=turn,
            )
        await service.damage(
            playthrough_db,
            user_id=user_id,
            target_id=goblin_ids[0],
            roll_id=damage_roll.id,
            hit_id=hit_id,
            turn_id=turn,
        )

        # -- After a whole fight: the exact same tables and columns, and
        # `state`'s own key set unchanged (nothing here brought the
        # character to zero, so not even `down` is added yet).
        assert await _table_names(playthrough_db) == EXPECTED_TABLES
        assert await _column_names(playthrough_db, "objects") == EXPECTED_OBJECTS_COLUMNS
        assert await _column_names(playthrough_db, "events") == EXPECTED_EVENTS_COLUMNS
        state_keys_after = await _state_keys(playthrough_db, run.id)
        assert state_keys_after == state_keys_before

    asyncio.run(_scenario())
