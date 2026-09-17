"""qa acceptance tests -- sprint 003/03 "adventure progress that cannot
contradict itself"
(`docs/intents/003-game-state/sprints/03-adventure-progress/brief.md`).

Black-box throughout: every assertion reads the real Postgres catalog and
data through `information_schema` / `pg_indexes` / plain SQL over the
shared `playthrough_db` fixture (`tests/playthrough/conftest.py`, sprint
01's deliverable), never model metadata and never an inspector -- the
migration and the models this sprint adds are parallel work items this
file never imports or reads (`app.modules.playthrough.models` does not
appear below on purpose).

All five criteria carry `@pytest.mark.database`: skipped under
`make backend-test` (no reachable Postgres, `--no-deps`), run for real
under `make backend-test-db`. No `pytest-asyncio` in this suite (`AGENTS.md`
gotchas) -- every async call is wrapped in a single `asyncio.run(...)` per
test.

Written against the fixed schema contract in the sprint plan, not against
the migration or the models themselves -- this suite is red until the
migration (WI1) and the models (WI2) land, and green once they do.
"""

import asyncio
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.ids import generate_id

BACKEND_ROOT = Path(__file__).resolve().parents[2]


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


async def _insert_adventure_run(
    session,
    run_id: str,
    campaign_run_id: str,
    *,
    adventure_id: str = "adventure-1",
    status: str | None = None,
    completed_at: str | None = None,
) -> None:
    columns = ["id", "campaign_run_id", "adventure_id"]
    params = {"id": run_id, "campaign_run_id": campaign_run_id, "adventure_id": adventure_id}
    if status is not None:
        columns.append("status")
        params["status"] = status
    if completed_at is not None:
        columns.append("completed_at")
        params["completed_at"] = completed_at

    await session.execute(
        text(
            f"INSERT INTO adventure_runs ({', '.join(columns)}) "
            f"VALUES ({', '.join(':' + c for c in columns)})"
        ),
        params,
    )


@pytest.mark.database
def test_ac1_migration_creates_adventure_runs_with_its_columns_and_no_scene_column(
    playthrough_db,
):
    # <- AC1: the real Postgres catalog carries `adventure_runs` with the
    # column set the brief names, and no `scene` column -- position belongs
    # to the creature and is a later sprint's.
    async def _inspect():
        tables = await playthrough_db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'adventure_runs'"
            )
        )
        assert {row.table_name for row in tables} == {"adventure_runs"}

        columns = await playthrough_db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'adventure_runs'"
            )
        )
        column_names = {row.column_name for row in columns}
        expected = {
            "campaign_run_id",
            "adventure_id",
            "status",
            "started_at",
            "completed_at",
            "updated_at",
        }
        assert expected <= column_names, column_names
        assert "scene" not in column_names

    asyncio.run(_inspect())


@pytest.mark.database
def test_ac2_repeat_adventure_in_the_same_campaign_run_violates_unique_constraint(
    playthrough_db,
):
    # <- AC2: one row per adventure entered -- a second row for the same
    # `(campaign_run_id, adventure_id)` raises.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac2-campaign")
        await playthrough_db.commit()

        await _insert_adventure_run(
            playthrough_db, generate_id(), campaign_run_id, adventure_id="ac2-adventure"
        )
        await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)):
            await _insert_adventure_run(
                playthrough_db, generate_id(), campaign_run_id, adventure_id="ac2-adventure"
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_second_active_adventure_in_same_run_raises_but_other_run_may_have_one(
    playthrough_db,
):
    # <- AC3: with one `active` row present, a second `active` row in the
    # same campaign run raises on the partial unique index, while an
    # `active` row in a different campaign run inserts fine.
    async def _scenario():
        campaign_run_id = generate_id()
        other_campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac3-campaign")
        await _insert_campaign_run(
            playthrough_db, other_campaign_run_id, campaign_id="ac3-other-campaign"
        )
        await playthrough_db.commit()

        await _insert_adventure_run(
            playthrough_db,
            generate_id(),
            campaign_run_id,
            adventure_id="ac3-adventure-1",
            status="active",
        )
        await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)):
            await _insert_adventure_run(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                adventure_id="ac3-adventure-2",
                status="active",
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()

        await _insert_adventure_run(
            playthrough_db,
            generate_id(),
            other_campaign_run_id,
            adventure_id="ac3-adventure-1",
            status="active",
        )
        await playthrough_db.commit()

        rows = await playthrough_db.execute(
            text(
                "SELECT campaign_run_id FROM adventure_runs WHERE status = 'active' "
                "AND campaign_run_id = ANY(:ids)"
            ),
            {"ids": [campaign_run_id, other_campaign_run_id]},
        )
        assert {row.campaign_run_id for row in rows} == {campaign_run_id, other_campaign_run_id}

        index = await playthrough_db.execute(
            text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'adventure_runs' "
                "AND indexname = 'uq_adventure_runs_active'"
            )
        )
        assert index.first() is not None

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_status_and_completed_at_are_tied_together_and_cascade_deletes(playthrough_db):
    # <- AC4: `status` accepts only `active` and `completed`; `completed`
    # without `completed_at`, and `completed_at` set on an `active` row,
    # both raise; deleting the parent `campaign_runs` row removes its
    # adventure runs.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac4-campaign")
        await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)):
            await _insert_adventure_run(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                adventure_id="ac4-bogus-status",
                status="bogus",
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()

        with pytest.raises((IntegrityError, DBAPIError)):
            await _insert_adventure_run(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                adventure_id="ac4-completed-no-time",
                status="completed",
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()

        with pytest.raises((IntegrityError, DBAPIError)):
            await _insert_adventure_run(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                adventure_id="ac4-active-with-time",
                status="active",
                completed_at="2026-01-01T00:00:00+00:00",
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()

        adventure_run_id = generate_id()
        await _insert_adventure_run(
            playthrough_db,
            adventure_run_id,
            campaign_run_id,
            adventure_id="ac4-cascade",
            status="completed",
            completed_at="2026-01-01T00:00:00+00:00",
        )
        await playthrough_db.commit()

        await playthrough_db.execute(
            text("DELETE FROM campaign_runs WHERE id = :id"), {"id": campaign_run_id}
        )
        await playthrough_db.commit()

        remaining = await playthrough_db.execute(
            text("SELECT id FROM adventure_runs WHERE id = :id"), {"id": adventure_run_id}
        )
        assert remaining.first() is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac5_downgrading_this_step_drops_the_table_and_leaves_sprint_02_intact(playthrough_db):
    # <- AC5: `alembic downgrade -1` drops `adventure_runs` and leaves
    # sprint 02's `campaign_runs` and `campaign_run_members` intact.
    async def _rollback_open_transaction():
        await playthrough_db.rollback()

    asyncio.run(_rollback_open_transaction())

    downgrade = subprocess.run(
        ["alembic", "downgrade", "-1"],
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
        assert "adventure_runs" not in table_names
        assert {"campaign_runs", "campaign_run_members"} <= table_names

    asyncio.run(_inspect())
