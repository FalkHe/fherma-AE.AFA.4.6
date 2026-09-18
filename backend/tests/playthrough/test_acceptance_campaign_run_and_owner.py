"""qa acceptance tests -- sprint 003/02 "a campaign run and its owner"
(`docs/intents/003-game-state/sprints/02-campaign-run-and-owner/brief.md`).

Black-box throughout: every assertion reads the real Postgres catalog and
data through `information_schema` / plain SQL over the shared
`playthrough_db` fixture (`tests/playthrough/conftest.py`, sprint 01's
deliverable), never model metadata and never an inspector -- the migration
and the models this sprint adds are a parallel work item this file never
imports or reads (`app.modules.playthrough.models` does not appear below on
purpose).

All four criteria carry `@pytest.mark.database`: skipped under
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


async def _insert_user(session, user_id: str, username: str) -> None:
    await session.execute(
        text(
            "INSERT INTO users (id, username, password_hash) "
            "VALUES (:id, :username, :password_hash)"
        ),
        {"id": user_id, "username": username, "password_hash": "not-a-real-hash"},
    )


async def _insert_campaign_run(
    session,
    run_id: str,
    *,
    campaign_id: str = "campaign-1",
    content_version: str = "v1",
    title: str | None = None,
    status: str | None = None,
) -> None:
    columns = ["id", "campaign_id", "content_version", "title"]
    params = {
        "id": run_id,
        "campaign_id": campaign_id,
        "content_version": content_version,
        "title": title,
    }
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


@pytest.mark.database
def test_ac1_migration_creates_campaign_runs_and_campaign_run_members_with_their_columns(
    playthrough_db,
):
    # <- AC1: the real Postgres catalog, not model metadata, carries both
    # tables and the column set the brief names on `campaign_runs`.
    async def _inspect():
        tables = await playthrough_db.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN "
                "('campaign_runs', 'campaign_run_members')"
            )
        )
        assert {row.table_name for row in tables} == {"campaign_runs", "campaign_run_members"}

        columns = await playthrough_db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'campaign_runs'"
            )
        )
        column_names = {row.column_name for row in columns}
        expected = {
            "campaign_id",
            "content_version",
            "title",
            "status",
            "model",
            "temperature",
            "personality_prompt_id",
            "system_prompt_override",
            "created_at",
            "updated_at",
        }
        assert expected <= column_names, column_names

    asyncio.run(_inspect())


@pytest.mark.database
def test_ac2_untitled_and_repeat_runs_of_the_same_campaign_insert_with_overrides_left_null(
    playthrough_db,
):
    # <- AC2: a run with `title = NULL` inserts, a second and third run of
    # the same `campaign_id` for the same user insert too, and the four
    # override columns -- never mentioned in the INSERT -- come back NULL
    # rather than some other default.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, "ac2-owner")

        run_ids = [generate_id() for _ in range(3)]
        for run_id in run_ids:
            await _insert_campaign_run(
                playthrough_db, run_id, campaign_id="ac2-campaign", title=None
            )
            await _insert_member(playthrough_db, generate_id(), run_id, user_id)
        await playthrough_db.commit()

        rows = await playthrough_db.execute(
            text(
                "SELECT id, title, model, temperature, personality_prompt_id, "
                "system_prompt_override FROM campaign_runs WHERE id = ANY(:ids)"
            ),
            {"ids": run_ids},
        )
        by_id = {row.id: row for row in rows}
        assert set(by_id) == set(run_ids)
        for run_id in run_ids:
            row = by_id[run_id]
            assert row.title is None
            assert row.model is None
            assert row.temperature is None
            assert row.personality_prompt_id is None
            assert row.system_prompt_override is None

        members = await playthrough_db.execute(
            text("SELECT campaign_run_id FROM campaign_run_members WHERE user_id = :user_id"),
            {"user_id": user_id},
        )
        assert {row.campaign_run_id for row in members} == set(run_ids)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_status_check_membership_uniqueness_and_owner_cascade(playthrough_db):
    # <- AC3: `status` accepts the five named values and rejects anything
    # else, a second membership row for the same run/user pair violates the
    # unique constraint, and deleting the owning user cascades onto the
    # member row.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, "ac3-owner")

        for status in ("setup", "ready", "active", "archived", "finished"):
            run_id = generate_id()
            await _insert_campaign_run(
                playthrough_db, run_id, campaign_id=f"ac3-{status}", status=status
            )
        await playthrough_db.commit()

        bad_run_id = generate_id()
        with pytest.raises((IntegrityError, DBAPIError)):
            await _insert_campaign_run(
                playthrough_db, bad_run_id, campaign_id="ac3-bad", status="bogus"
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()

        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id, campaign_id="ac3-membership")
        member_id = generate_id()
        await _insert_member(playthrough_db, member_id, run_id, user_id)
        await playthrough_db.commit()

        with pytest.raises((IntegrityError, DBAPIError)):
            await _insert_member(playthrough_db, generate_id(), run_id, user_id)
            await playthrough_db.commit()
        await playthrough_db.rollback()

        await playthrough_db.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
        await playthrough_db.commit()

        remaining = await playthrough_db.execute(
            text("SELECT id FROM campaign_run_members WHERE id = :id"), {"id": member_id}
        )
        assert remaining.first() is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_downgrading_this_step_alone_leaves_no_trace_and_downgrade_base_stays_clean(
    playthrough_db,
):
    # <- AC4: `downgrade 0002` drops exactly this sprint's two tables and
    # leaves the baseline (`users`, `sessions`) plus SRD's own table
    # untouched; `downgrade base` on top of that still exits clean.
    async def _rollback_open_transaction():
        await playthrough_db.rollback()

    asyncio.run(_rollback_open_transaction())

    downgrade_step = subprocess.run(
        ["alembic", "downgrade", "0002"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert downgrade_step.returncode == 0, downgrade_step.stdout + downgrade_step.stderr

    async def _inspect():
        tables = await playthrough_db.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        table_names = {row.table_name for row in tables}
        assert table_names == {"users", "sessions", "srd_rules", "alembic_version"}, table_names

    asyncio.run(_inspect())

    downgrade_base = subprocess.run(
        ["alembic", "downgrade", "base"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )
    assert downgrade_base.returncode == 0, downgrade_base.stdout + downgrade_base.stderr
