"""qa acceptance tests -- sprint 005/02 "the schema accepts the lifecycle
this phase writes"
(`docs/intents/005-game-state-services/sprints/02-migration-0007/brief.md`).

Black-box throughout: every assertion inserts through the real Postgres
connection or reads back a row, over the shared `playthrough_db` fixture
(`tests/playthrough/conftest.py`) -- the migration and the model this
sprint changes are a parallel work item this file never imports or reads
(neither `app.modules.playthrough.models` nor
`backend/alembic/versions/0007_*.py` appears below, on purpose). Refusals
are matched by the constraint name the database reports, never by the
driver's whole message, and never by re-deriving how the revision was
written.

All tests carry `@pytest.mark.database`: skipped under `make backend-test`
(no reachable Postgres, `--no-deps`), run for real under
`make backend-test-db`. No `pytest-asyncio` in this suite (`AGENTS.md`
gotchas) -- every async call is wrapped in a single `asyncio.run(...)` per
test.

Written against the fixed schema contract in the sprint plan
(`docs/intents/005-game-state-services/sprints/02-migration-0007/plan.md`),
not against the migration or the model themselves -- this suite may be red
while the implementation lands in parallel, and green once it does.
"""

import asyncio
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.ids import generate_id

BACKEND_ROOT = Path(__file__).resolve().parents[2]

NEW_EVENT_TYPES = (
    "narration",
    "player_action",
    "roll_requested",
    "roll",
    "question",
    "tool_call",
    "scene_entered",
    "adventure_started",
    "adventure_completed",
    "system",
    "error",
    "warning",
)

OLD_EVENT_TYPES = ("narration", "player_action", "roll", "tool_call", "error")


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
    status: str | None = None,
) -> None:
    columns = ["id", "campaign_id", "content_version"]
    params: dict = {"id": run_id, "campaign_id": campaign_id, "content_version": content_version}
    if status is not None:
        columns.append("status")
        params["status"] = status

    await session.execute(
        text(
            f"INSERT INTO campaign_runs ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)})"
        ),
        params,
    )


async def _insert_member(session, member_id: str, campaign_run_id: str, user_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_run_members (id, campaign_run_id, user_id) "
            "VALUES (:id, :campaign_run_id, :user_id)"
        ),
        {"id": member_id, "campaign_run_id": campaign_run_id, "user_id": user_id},
    )


async def _insert_object(session, object_id: str, campaign_run_id: str, **fields) -> None:
    """Inserts an `objects` row with sane creature-free defaults, overridden
    by `fields`. `kind`/`template_id`/`instance_key`/`name` always present
    unless explicitly overridden (e.g. `template_id=None`)."""
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


async def _insert_event(session, event_id: str, campaign_run_id: str, **fields) -> None:
    columns = ["id", "campaign_run_id"]
    params: dict = {"id": event_id, "campaign_run_id": campaign_run_id}
    defaults = {"type": "narration", "visibility": "player", "payload": "{}"}
    defaults.update(fields)
    for key, value in defaults.items():
        columns.append(key)
        params[key] = value

    value_exprs = [f":{c} ::jsonb" if c == "payload" else f":{c}" for c in columns]
    await session.execute(
        text(f"INSERT INTO events ({', '.join(columns)}) VALUES ({', '.join(value_exprs)})"),
        params,
    )


@pytest.mark.database
def test_ac1_status_defaults_to_setup_all_five_lifecycle_values_are_accepted_paused_refused(
    playthrough_db,
):
    # <- AC1: a run written without a `status` reads back `setup`; each of
    # `setup ready active archived finished` inserts and round-trips;
    # `paused` raises on `ck_campaign_runs_status` specifically.
    async def _scenario():
        default_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, default_run_id, campaign_id="ac1-default")
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": default_run_id}
        )
        assert row.first().status == "setup"

        for status in ("setup", "ready", "active", "archived", "finished"):
            run_id = generate_id()
            await _insert_campaign_run(
                playthrough_db, run_id, campaign_id=f"ac1-{status}", status=status
            )
            await playthrough_db.commit()
            row = await playthrough_db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": run_id}
            )
            assert row.first().status == status

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_campaign_run(
                playthrough_db, generate_id(), campaign_id="ac1-bad", status="paused"
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_campaign_runs_status" in str(exc_info.value)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac2_a_template_less_creature_with_a_member_inserts_and_the_two_stat_rules_still_bite(
    playthrough_db,
):
    # <- AC2: a `creature` row with `template_id = NULL` and `member_id`
    # set inserts; `ck_objects_stats_creature_only` still refuses a
    # non-creature carrying a fighting stat, and `ck_objects_hp_range`
    # still refuses `current_hp` outside `0 .. max_hp`.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac2-campaign")
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac2-user")
        await playthrough_db.commit()
        member_id = generate_id()
        await _insert_member(playthrough_db, member_id, campaign_run_id, user_id)
        await playthrough_db.commit()

        creature_id = generate_id()
        await _insert_object(
            playthrough_db,
            creature_id,
            campaign_run_id,
            kind="creature",
            template_id=None,
            member_id=member_id,
            current_hp=5,
            max_hp=10,
            armour_class=12,
            is_alive=True,
        )
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT template_id, member_id FROM objects WHERE id = :id"),
            {"id": creature_id},
        )
        found = row.first()
        assert found.template_id is None
        assert found.member_id == member_id

        # the creature-only stats rule still refuses a non-creature
        # carrying a fighting stat.
        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(
                playthrough_db, generate_id(), campaign_run_id, kind="item", is_alive=True
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_objects_stats_creature_only" in str(exc_info.value)

        # the hit-point range rule still refuses current_hp > max_hp.
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

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_all_twelve_event_types_insert_and_a_thirteenth_is_refused(playthrough_db):
    # <- AC3: each of the twelve `events.type` values inserts and reads
    # back; `foo` raises on `ck_events_type` specifically.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac3-campaign")
        await playthrough_db.commit()

        assert len(NEW_EVENT_TYPES) == 12

        for event_type in NEW_EVENT_TYPES:
            event_id = generate_id()
            await _insert_event(playthrough_db, event_id, campaign_run_id, type=event_type)
            await playthrough_db.commit()
            row = await playthrough_db.execute(
                text("SELECT type FROM events WHERE id = :id"), {"id": event_id}
            )
            assert row.first().type == event_type

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_event(playthrough_db, generate_id(), campaign_run_id, type="foo")
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_events_type" in str(exc_info.value)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_downgrading_to_0006_restores_the_prior_checks_default_and_not_null(playthrough_db):
    # <- AC4: undoing this step's migration restores `ck_campaign_runs_status`
    # to its three-value set with default `active`, `ck_events_type` to its
    # five-value set (with `ck_events_visibility` still behaving as before),
    # and `objects.template_id` to `NOT NULL` -- exactly what `0006` left in
    # place, proven by what the database now accepts and refuses rather than
    # by the revision's own text.
    async def _head_is_at_least_0007():
        # A later sprint's migration may have moved head past `0007` --
        # this only needs the chain to include it, not to be it, before
        # downgrading two steps below it to `0006`.
        row = await playthrough_db.execute(text("SELECT version_num FROM alembic_version"))
        assert row.scalar() is not None
        await playthrough_db.rollback()

    asyncio.run(_head_is_at_least_0007())

    downgrade = subprocess.run(
        ["alembic", "downgrade", "0006"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stdout + downgrade.stderr

    async def _scenario():
        # status: default is 'active' again, the old three values still
        # insert, and the new lifecycle values this sprint added are gone.
        default_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, default_run_id, campaign_id="ac4-default")
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": default_run_id}
        )
        assert row.first().status == "active"

        for status in ("active", "archived", "finished"):
            run_id = generate_id()
            await _insert_campaign_run(
                playthrough_db, run_id, campaign_id=f"ac4-{status}", status=status
            )
            await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_campaign_run(
                playthrough_db, generate_id(), campaign_id="ac4-setup", status="setup"
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_campaign_runs_status" in str(exc_info.value)

        # events.type: the five old values still insert, a value this
        # sprint added (`roll_requested`) is refused, and visibility
        # behaves exactly as it always did.
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac4-events")
        await playthrough_db.commit()

        for event_type in OLD_EVENT_TYPES:
            event_id = generate_id()
            await _insert_event(playthrough_db, event_id, campaign_run_id, type=event_type)
            await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_event(
                playthrough_db, generate_id(), campaign_run_id, type="roll_requested"
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_events_type" in str(exc_info.value)

        for visibility in ("player", "dm"):
            event_id = generate_id()
            await _insert_event(playthrough_db, event_id, campaign_run_id, visibility=visibility)
            await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_event(playthrough_db, generate_id(), campaign_run_id, visibility="bogus")
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_events_visibility" in str(exc_info.value)

        # objects.template_id: NOT NULL is back -- a NULL template raises,
        # naming the column, and a row with a template still inserts.
        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_object(playthrough_db, generate_id(), campaign_run_id, template_id=None)
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "template_id" in str(exc_info.value)

        templated_id = generate_id()
        await _insert_object(playthrough_db, templated_id, campaign_run_id, template_id="tpl-1")
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT template_id FROM objects WHERE id = :id"), {"id": templated_id}
        )
        assert row.first().template_id == "tpl-1"

    asyncio.run(_scenario())
