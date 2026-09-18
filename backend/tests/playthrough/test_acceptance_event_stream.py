"""qa acceptance tests -- sprint 003/05 "an append-only, ordered, filterable
transcript" (`docs/intents/003-game-state/sprints/05-event-stream/brief.md`).

Black-box throughout: every assertion reads the real Postgres catalog and
data through `information_schema` / `pg_constraint` / plain SQL over the
shared `playthrough_db` fixture (`tests/playthrough/conftest.py`, sprint
01's deliverable), never model metadata and never an inspector -- the
migration and the model this sprint adds are parallel work items this file
never imports or reads (`app.modules.playthrough.models` does not appear
below on purpose, and neither does `backend/alembic/versions/0006_events.py`).

All tests carry `@pytest.mark.database`: skipped under `make backend-test`
(no reachable Postgres, `--no-deps`), run for real under
`make backend-test-db`. No `pytest-asyncio` in this suite (`AGENTS.md`
gotchas) -- every async call is wrapped in a single `asyncio.run(...)` per
test.

Written against the fixed schema contract in the sprint plan, not against
the migration or the model itself -- this suite is red until the migration
(WI1) and the model (WI2) land, and green once they do.

Four measured facts shape these tests (sprint plan, `research.md`):
`now()` is transaction-start time (several rows inserted in one transaction
share one `created_at`, so AC1 orders by `id` alone); the id generator
(`app.core.ids.generate_id`) is monotonic within a millisecond, so ids
minted back to back sort in write order; `CHAR` pads short literals on
read, so `turn_id` values are full-length generated ids, never short
literals; `SUM` over a `NUMERIC` column arrives as a `decimal.Decimal`,
never a float.
"""

import asyncio
import subprocess
from decimal import Decimal
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


async def _insert_event(session, event_id: str, campaign_run_id: str, **fields) -> None:
    """Inserts an `events` row with sane defaults, overridden by `fields`.
    `type`, `visibility` and `payload` always required; everything else
    stays NULL unless passed."""
    columns = ["id", "campaign_run_id"]
    params: dict = {"id": event_id, "campaign_run_id": campaign_run_id}
    defaults = {
        "type": "narration",
        "visibility": "player",
        "payload": "{}",
    }
    defaults.update(fields)
    for key, value in defaults.items():
        columns.append(key)
        params[key] = value

    payload_cast = " ::jsonb" if "payload" in defaults else ""
    value_exprs = []
    for c in columns:
        if c == "payload":
            value_exprs.append(f":{c}{payload_cast}")
        else:
            value_exprs.append(f":{c}")

    await session.execute(
        text(f"INSERT INTO events ({', '.join(columns)}) VALUES ({', '.join(value_exprs)})"),
        params,
    )


@pytest.mark.database
def test_ac1_events_read_back_in_write_order_by_id_alone(playthrough_db):
    # <- AC1: several events written without timestamps of their own, read
    # back with `ORDER BY id`, come out in write order. `now()` is
    # transaction-start time so every row in this single transaction shares
    # one `created_at` -- ordering must never touch it.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac1-campaign")
        await playthrough_db.commit()

        ids = [generate_id() for _ in range(5)]
        for event_id in ids:
            await _insert_event(playthrough_db, event_id, campaign_run_id)
        await playthrough_db.commit()

        rows = await playthrough_db.execute(
            text(
                "SELECT id, created_at FROM events WHERE campaign_run_id = :campaign_run_id "
                "ORDER BY id"
            ),
            {"campaign_run_id": campaign_run_id},
        )
        rows = rows.all()
        assert [row.id for row in rows] == ids
        # every row shares one transaction-start timestamp -- proof that
        # ordering above cannot have come from `created_at`.
        assert len({row.created_at for row in rows}) == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac2_player_visibility_filter_skips_dm_events_with_no_gap(playthrough_db):
    # <- AC2: a read filtered to `visibility = 'player'` omits a `dm` event
    # written between two player events, returns the two with no gap or
    # placeholder, while the `dm` row is still there on an unfiltered read.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac2-campaign")
        await playthrough_db.commit()

        first_id = generate_id()
        hidden_id = generate_id()
        second_id = generate_id()
        await _insert_event(playthrough_db, first_id, campaign_run_id, visibility="player")
        await _insert_event(playthrough_db, hidden_id, campaign_run_id, visibility="dm")
        await _insert_event(playthrough_db, second_id, campaign_run_id, visibility="player")
        await playthrough_db.commit()

        player_rows = await playthrough_db.execute(
            text(
                "SELECT id FROM events WHERE campaign_run_id = :campaign_run_id "
                "AND visibility = 'player' ORDER BY id"
            ),
            {"campaign_run_id": campaign_run_id},
        )
        assert [row.id for row in player_rows] == [first_id, second_id]

        unfiltered_rows = await playthrough_db.execute(
            text("SELECT id FROM events WHERE campaign_run_id = :campaign_run_id ORDER BY id"),
            {"campaign_run_id": campaign_run_id},
        )
        assert [row.id for row in unfiltered_rows] == [first_id, hidden_id, second_id]

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_type_and_visibility_are_restricted_to_their_declared_values(playthrough_db):
    # <- AC3: `type` accepts exactly the twelve declared values and raises
    # (`ck_events_type`) on anything else; `visibility` accepts exactly
    # `player` and `dm` and raises (`ck_events_visibility`) on anything
    # else.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac3-campaign")
        await playthrough_db.commit()

        for event_type in (
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
        ):
            event_id = generate_id()
            await _insert_event(playthrough_db, event_id, campaign_run_id, type=event_type)
            await playthrough_db.commit()
            row = await playthrough_db.execute(
                text("SELECT type FROM events WHERE id = :id"), {"id": event_id}
            )
            assert row.first().type == event_type

        for visibility in ("player", "dm"):
            event_id = generate_id()
            await _insert_event(playthrough_db, event_id, campaign_run_id, visibility=visibility)
            await playthrough_db.commit()
            row = await playthrough_db.execute(
                text("SELECT visibility FROM events WHERE id = :id"), {"id": event_id}
            )
            assert row.first().visibility == visibility

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_event(playthrough_db, generate_id(), campaign_run_id, type="bogus")
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_events_type" in str(exc_info.value)

        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await _insert_event(playthrough_db, generate_id(), campaign_run_id, visibility="bogus")
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_events_visibility" in str(exc_info.value)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_cost_usd_sums_exactly_overall_and_per_turn(playthrough_db):
    # <- AC4: `cost_usd` is `NUMERIC(12,6)` -- three costs sum to the exact
    # decimal total, and `SUM` grouped by `turn_id` gives the per-turn
    # figure. No total is stored anywhere. `turn_id` uses full-length
    # generated ids -- `CHAR` pads short literals on read, which would break
    # the grouping.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac4-campaign")
        await playthrough_db.commit()

        turn_a = generate_id()
        turn_b = generate_id()
        costs = [
            (turn_a, Decimal("0.000123")),
            (turn_a, Decimal("1.500000")),
            (turn_b, Decimal("2.250001")),
        ]
        for turn_id, cost in costs:
            await _insert_event(
                playthrough_db,
                generate_id(),
                campaign_run_id,
                turn_id=turn_id,
                cost_usd=cost,
            )
        await playthrough_db.commit()

        total_row = await playthrough_db.execute(
            text(
                "SELECT SUM(cost_usd) AS total FROM events WHERE campaign_run_id = :campaign_run_id"
            ),
            {"campaign_run_id": campaign_run_id},
        )
        total = total_row.first().total
        assert isinstance(total, Decimal)
        assert total == Decimal("3.750124")

        per_turn_rows = await playthrough_db.execute(
            text(
                "SELECT turn_id, SUM(cost_usd) AS total FROM events "
                "WHERE campaign_run_id = :campaign_run_id GROUP BY turn_id"
            ),
            {"campaign_run_id": campaign_run_id},
        )
        per_turn = {row.turn_id.strip(): row.total for row in per_turn_rows}
        assert per_turn[turn_a] == Decimal("1.500123")
        assert per_turn[turn_b] == Decimal("2.250001")
        for value in per_turn.values():
            assert isinstance(value, Decimal)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac5_actor_is_cleared_on_member_delete_while_run_delete_cascades(playthrough_db):
    # <- AC5: `actor_member_id` is nullable, accepts a member id, and is set
    # to NULL (not cascaded) when that member row is deleted, while deleting
    # the campaign run does remove its events.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id, campaign_id="ac5-campaign")
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac5-user")
        await playthrough_db.commit()
        member_id = generate_id()
        await _insert_member(playthrough_db, member_id, campaign_run_id, user_id)
        await playthrough_db.commit()

        event_id = generate_id()
        await _insert_event(playthrough_db, event_id, campaign_run_id, actor_member_id=member_id)
        await playthrough_db.commit()

        row = await playthrough_db.execute(
            text("SELECT actor_member_id FROM events WHERE id = :id"), {"id": event_id}
        )
        assert row.first().actor_member_id == member_id

        await playthrough_db.execute(
            text("DELETE FROM campaign_run_members WHERE id = :id"), {"id": member_id}
        )
        await playthrough_db.commit()

        row = await playthrough_db.execute(
            text("SELECT actor_member_id FROM events WHERE id = :id"), {"id": event_id}
        )
        assert row.first().actor_member_id is None

        surviving = await playthrough_db.execute(
            text("SELECT id FROM events WHERE id = :id"), {"id": event_id}
        )
        assert surviving.first() is not None

        await playthrough_db.execute(
            text("DELETE FROM campaign_runs WHERE id = :id"), {"id": campaign_run_id}
        )
        await playthrough_db.commit()

        gone = await playthrough_db.execute(
            text("SELECT id FROM events WHERE id = :id"), {"id": event_id}
        )
        assert gone.first() is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac5_downgrading_this_step_drops_events_and_leaves_earlier_tables_intact(
    playthrough_db,
):
    # <- AC5: undoing this step's migration drops `events` and leaves the
    # earlier tables (`campaign_runs`, `campaign_run_members`,
    # `adventure_runs`, `objects`) intact. Named as revision `0005` (this
    # step's `down_revision`), not `-1`: `-1` resolves against the
    # database's *current* revision, so it silently targets whatever the
    # chain's head has grown to by the time a later sprint's migration lands
    # on top -- naming the revision keeps this assertion true as the chain
    # grows.
    async def _rollback_open_transaction():
        await playthrough_db.rollback()

    asyncio.run(_rollback_open_transaction())

    downgrade = subprocess.run(
        ["alembic", "downgrade", "0005"],
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
        assert "events" not in table_names
        assert {
            "campaign_runs",
            "campaign_run_members",
            "adventure_runs",
            "objects",
        } <= table_names

    asyncio.run(_inspect())
