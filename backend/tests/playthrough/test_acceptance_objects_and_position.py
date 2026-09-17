"""qa acceptance tests -- sprint 003/04 "objects that hold only what the
content declares"
(`docs/intents/003-game-state/sprints/04-objects-and-position/brief.md`).

Black-box throughout: every assertion reads the real Postgres catalog and
data through `information_schema` / `pg_indexes` / `pg_constraint` / plain
SQL over the shared `playthrough_db` fixture (`tests/playthrough/conftest.py`,
sprint 01's deliverable), never model metadata and never an inspector -- the
migration and the model this sprint adds are parallel work items this file
never imports or reads (`app.modules.playthrough.models` does not appear
below on purpose).

All tests carry `@pytest.mark.database`: skipped under `make backend-test`
(no reachable Postgres, `--no-deps`), run for real under
`make backend-test-db`. No `pytest-asyncio` in this suite (`AGENTS.md`
gotchas) -- every async call is wrapped in a single `asyncio.run(...)` per
test.

Written against the fixed schema contract in the sprint plan, not against
the migration or the model itself -- this suite is red until the migration
(WI1) and the model (WI2) land, and green once they do.

The brief's acceptance criteria are numbered AC1, AC3, AC4, AC5 -- there is
genuinely no AC2 (a numbering slip upstream, not a missing rule); the first
test below stands in for it, over the table's shape and its cascade instead
of a numbered rule.
"""

import asyncio
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.ids import generate_id

BACKEND_ROOT = Path(__file__).resolve().parents[2]


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _insert_campaign_run(
    session,
    run_id: str,
    *,
    campaign_id: str = "campaign-1",
    content_version: str = "v1",
) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_runs (id, campaign_id, content_version) "
            "VALUES (:id, :campaign_id, :content_version)"
        ),
        {"id": run_id, "campaign_id": campaign_id, "content_version": content_version},
    )


async def _insert_member(session, member_id: str, campaign_run_id: str, user_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_run_members (id, campaign_run_id, user_id) "
            "VALUES (:id, :campaign_run_id, :user_id)"
        ),
        {"id": member_id, "campaign_run_id": campaign_run_id, "user_id": user_id},
    )


async def _insert_adventure_run(
    session, run_id: str, campaign_run_id: str, *, adventure_id: str = "adventure-1"
) -> None:
    await session.execute(
        text(
            "INSERT INTO adventure_runs (id, campaign_run_id, adventure_id) "
            "VALUES (:id, :campaign_run_id, :adventure_id)"
        ),
        {"id": run_id, "campaign_run_id": campaign_run_id, "adventure_id": adventure_id},
    )


async def _insert_object(session, object_id: str, campaign_run_id: str, **fields) -> None:
    """Inserts an `objects` row with sane creature-free defaults, overridden
    by `fields`. `kind`/`template_id`/`instance_key`/`name` always required;
    everything else stays NULL unless passed."""
    columns = ["id", "campaign_run_id"]
    params: dict = {"id": object_id, "campaign_run_id": campaign_run_id}
    defaults = {
        "kind": "item",
        "template_id": "tpl-1",
        "instance_key": f"key-{object_id}",
        "name": "Thing",
    }
    defaults.update(fields)
    for key, value in defaults.items():
        columns.append(key)
        params[key] = value

    await session.execute(
        text(
            f"INSERT INTO objects ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)})"
        ),
        params,
    )


@pytest.mark.database
def test_ac0_objects_table_exists_with_provenance_distinct_from_position_and_cascades(
    playthrough_db,
):
    # <- stands in for the brief's absent AC2: the `objects` table exists
    # with both a provenance pair (`source_adventure_id`, `source_scene_id`)
    # and a distinct position pair (`adventure_run_id`, `scene_id`) --
    # objects exist before their adventure is entered -- and deleting the
    # parent `campaign_runs` row removes its objects.
    async def _scenario():
        tables = await playthrough_db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'objects'"
            )
        )
        assert {row.table_name for row in tables} == {"objects"}

        columns = await playthrough_db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'objects'"
            )
        )
        column_names = {row.column_name for row in columns}
        expected = {
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
        assert expected <= column_names, column_names
        # provenance and position are distinct column pairs, not aliases of
        # one another.
        assert {"source_adventure_id", "source_scene_id"} != {"adventure_run_id", "scene_id"}

        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac0-campaign")
        await playthrough_db.commit()

        object_id = generate_id()
        await _insert_object(
            playthrough_db,
            object_id,
            campaign_run_id,
            source_adventure_id="ac0-adventure",
            source_scene_id="ac0-scene",
        )
        await playthrough_db.commit()

        await playthrough_db.execute(
            text("DELETE FROM campaign_runs WHERE id = :id"), {"id": campaign_run_id}
        )
        await playthrough_db.commit()

        remaining = await playthrough_db.execute(
            text("SELECT id FROM objects WHERE id = :id"), {"id": object_id}
        )
        assert remaining.first() is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac1_kind_is_restricted_and_only_a_creature_may_carry_the_four_fighting_stats(
    playthrough_db,
):
    # <- AC1: `kind` accepts only `creature`, `item`, `fixture`; a `creature`
    # row requires all four of `current_hp`, `max_hp`, `armour_class`,
    # `is_alive`; an `item` or `fixture` carrying any one of them raises on
    # `ck_objects_stats_creature_only` specifically.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac1-campaign")
        await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(playthrough_db, generate_id(), campaign_run_id, kind="monster")
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_objects_kind" in str(exc_info.value)

        # a creature missing any one of the four stats raises: `current_hp`
        # and `max_hp` alone also trip the pairing half of
        # `ck_objects_hp_range`, so only the two range-independent fields
        # (`armour_class`, `is_alive`) are asserted against the check name
        # itself; all four are asserted to raise.
        full_stats = {
            "current_hp": 5,
            "max_hp": 10,
            "armour_class": 12,
            "is_alive": True,
        }
        for missing in full_stats:
            incomplete = {k: v for k, v in full_stats.items() if k != missing}
            with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
                await _insert_object(
                    playthrough_db,
                    generate_id(),
                    campaign_run_id,
                    kind="creature",
                    **incomplete,
                )
                await playthrough_db.commit()
            await playthrough_db.rollback()
            if missing in ("armour_class", "is_alive"):
                assert "ck_objects_stats_creature_only" in str(exc_info.value)

        # a creature with all four inserts.
        creature_id = generate_id()
        await _insert_object(
            playthrough_db, creature_id, campaign_run_id, kind="creature", **full_stats
        )
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT kind FROM objects WHERE id = :id"), {"id": creature_id}
        )
        assert row.first().kind == "creature"

        # an item or fixture carrying any one of the four stats raises;
        # isolating `armour_class`/`is_alive` (independent of the hp pairing
        # rule) confirms the failure names `ck_objects_stats_creature_only`
        # specifically, not the hp range check.
        for kind in ("item", "fixture"):
            for key, value in full_stats.items():
                with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
                    await _insert_object(
                        playthrough_db,
                        generate_id(),
                        campaign_run_id,
                        kind=kind,
                        **{key: value},
                    )
                    await playthrough_db.commit()
                await playthrough_db.rollback()
                if key in ("armour_class", "is_alive"):
                    assert "ck_objects_stats_creature_only" in str(exc_info.value)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_current_hp_must_stay_within_max_hp_but_zero_hp_may_be_stable_or_dead(
    playthrough_db,
):
    # <- AC3: `current_hp` outside `0 .. max_hp` raises on
    # `ck_objects_hp_range`; at `current_hp = 0` both `is_alive` values are
    # accepted -- stable is not dead.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac3-campaign")
        await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                kind="creature",
                current_hp=-1,
                max_hp=10,
                armour_class=12,
                is_alive=True,
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_objects_hp_range" in str(exc_info.value)

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                kind="creature",
                current_hp=11,
                max_hp=10,
                armour_class=12,
                is_alive=True,
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_objects_hp_range" in str(exc_info.value)

        stable_id = generate_id()
        await _insert_object(
            playthrough_db,
            stable_id,
            campaign_run_id,
            kind="creature",
            current_hp=0,
            max_hp=10,
            armour_class=12,
            is_alive=True,
        )
        dead_id = generate_id()
        await _insert_object(
            playthrough_db,
            dead_id,
            campaign_run_id,
            kind="creature",
            current_hp=0,
            max_hp=10,
            armour_class=12,
            is_alive=False,
        )
        await playthrough_db.commit()

        rows = await playthrough_db.execute(
            text("SELECT id, is_alive FROM objects WHERE id = ANY(:ids)"),
            {"ids": [stable_id, dead_id]},
        )
        by_id = {row.id: row.is_alive for row in rows}
        assert by_id == {stable_id: True, dead_id: False}

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_ownership_excludes_position_and_position_is_whole_or_absent(playthrough_db):
    # <- AC4: a row with `owner_object_id` set and a position raises on
    # `ck_objects_carried` specifically, not on `ck_objects_position`;
    # `adventure_run_id`/`scene_id` must be both set or both NULL, and that
    # raises on `ck_objects_position` specifically; a row with neither owner
    # nor position inserts -- it belongs to an adventure nobody has entered.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac4-campaign")
        await playthrough_db.commit()
        adventure_run_id = generate_id()
        await _insert_adventure_run(playthrough_db, adventure_run_id, campaign_run_id)
        await playthrough_db.commit()

        owner_id = generate_id()
        await _insert_object(playthrough_db, owner_id, campaign_run_id)
        await playthrough_db.commit()

        # owned and positioned: ck_objects_carried fires, not ck_objects_position.
        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                owner_object_id=owner_id,
                adventure_run_id=adventure_run_id,
                scene_id="scene-1",
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_objects_carried" in str(exc_info.value)
        assert "ck_objects_position" not in str(exc_info.value)

        # half a position: ck_objects_position fires.
        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                adventure_run_id=adventure_run_id,
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_objects_position" in str(exc_info.value)

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                scene_id="scene-1",
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_objects_position" in str(exc_info.value)

        # neither owner nor position: inserts.
        unplaced_id = generate_id()
        await _insert_object(playthrough_db, unplaced_id, campaign_run_id)
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT owner_object_id, adventure_run_id, scene_id FROM objects WHERE id = :id"),
            {"id": unplaced_id},
        )
        found = row.first()
        assert (found.owner_object_id, found.adventure_run_id, found.scene_id) == (
            None,
            None,
            None,
        )

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac5_a_member_may_hold_two_objects_but_instance_key_is_unique_per_campaign_run(
    playthrough_db,
):
    # <- AC5: two `objects` rows whose `member_id` points at the same member
    # insert -- nothing restricts the count; the same `instance_key` twice
    # in one campaign run raises on the composite unique constraint.
    async def _scenario():
        constraint_rows = await playthrough_db.execute(
            text(
                "SELECT tc.constraint_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "WHERE tc.table_name = 'objects' AND tc.constraint_type = 'UNIQUE' "
                "AND kcu.column_name = 'instance_key'"
            )
        )
        constraint_names = {row.constraint_name for row in constraint_rows}
        assert len(constraint_names) == 1, constraint_names
        composite_unique_constraint = next(iter(constraint_names))

        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac5-campaign")
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac5-user")
        await playthrough_db.commit()
        member_id = generate_id()
        await _insert_member(playthrough_db, member_id, campaign_run_id, user_id)
        await playthrough_db.commit()

        first_id = generate_id()
        second_id = generate_id()
        await _insert_object(
            playthrough_db,
            first_id,
            campaign_run_id,
            member_id=member_id,
            instance_key="pc:member:1",
        )
        await _insert_object(
            playthrough_db,
            second_id,
            campaign_run_id,
            member_id=member_id,
            instance_key="pc:member:2",
        )
        await playthrough_db.commit()

        rows = await playthrough_db.execute(
            text("SELECT id FROM objects WHERE member_id = :member_id"), {"member_id": member_id}
        )
        assert {row.id for row in rows} == {first_id, second_id}

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                instance_key="pc:member:1",
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert composite_unique_constraint in str(exc_info.value)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac5_downgrading_this_step_drops_objects_and_leaves_earlier_tables_intact(
    playthrough_db,
):
    # <- AC5: undoing this step's migration drops `objects` and leaves the
    # earlier tables (`campaign_runs`, `campaign_run_members`,
    # `adventure_runs`) intact. Named as revision `0004` (this step's
    # `down_revision`), not `-1`: `-1` resolves against the database's
    # *current* revision, so it silently targets whatever the chain's head
    # has grown to by the time a later sprint's migration lands on top --
    # naming the revision keeps this assertion true as the chain grows.
    async def _rollback_open_transaction():
        await playthrough_db.rollback()

    asyncio.run(_rollback_open_transaction())

    downgrade = subprocess.run(
        ["alembic", "downgrade", "0004"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    async def _inspect():
        tables = await playthrough_db.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        table_names = {row.table_name for row in tables}
        assert "objects" not in table_names
        assert {"campaign_runs", "campaign_run_members", "adventure_runs"} <= table_names

    asyncio.run(_inspect())
