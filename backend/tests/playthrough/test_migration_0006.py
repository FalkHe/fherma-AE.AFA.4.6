"""WI2: `0006_events` -- revision chain, the exact shape of the `events`
table (I1) and `upgrade()`/`downgrade()` symmetry. Engine-free:
`alembic.op` is a module-level proxy, so its individual functions are
monkeypatched with recording stand-ins rather than ever executing against a
real connection -- `run_migrations_online()` is never called, matching
`backend/tests/conftest.py`'s suite-wide ban on a real engine."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

MIGRATION_PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0006_events.py"


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("playthrough_migration_0006", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def recorded_calls(monkeypatch, migration):
    """Replaces every `op` function the migration calls with a stand-in that
    only records the call, and asserts nothing else on `op` is touched."""
    calls = []

    def _recorder(name):
        def _record(*args, **kwargs):
            calls.append((name, args, kwargs))

        return _record

    for name in ("create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(migration.op, name, _recorder(name))

    return calls


def _columns(create_table_args):
    return {arg.name: arg for arg in create_table_args[1:] if isinstance(arg, sa.Column)}


def _constraints(create_table_args, kind):
    return [arg for arg in create_table_args[1:] if isinstance(arg, kind)]


def test_revision_is_0006(migration):
    assert migration.revision == "0006"


def test_down_revision_is_0005(migration):
    assert migration.down_revision == "0005"


def test_upgrade_creates_events_then_its_two_indexes(migration, recorded_calls):
    migration.upgrade()

    assert [call[0] for call in recorded_calls] == [
        "create_table",
        "create_index",
        "create_index",
    ]

    _, table_args, _ = recorded_calls[0]
    assert table_args[0] == "events"
    columns = _columns(table_args)
    assert set(columns) == {
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
    not_null = {
        "id",
        "campaign_run_id",
        "type",
        "visibility",
        "payload",
        "created_at",
    }
    for name, column in columns.items():
        assert column.nullable == (name not in not_null), name

    assert isinstance(columns["id"].type, sa.CHAR) and columns["id"].type.length == 26
    assert isinstance(columns["campaign_run_id"].type, sa.CHAR)
    assert isinstance(columns["actor_member_id"].type, sa.CHAR)
    assert isinstance(columns["turn_id"].type, sa.CHAR)
    assert isinstance(columns["type"].type, sa.String) and columns["type"].type.length == 32
    assert (
        isinstance(columns["visibility"].type, sa.String) and columns["visibility"].type.length == 8
    )
    assert isinstance(columns["payload"].type, JSONB)
    assert columns["payload"].server_default is None
    assert isinstance(columns["prompt_tokens"].type, sa.Integer)
    assert isinstance(columns["completion_tokens"].type, sa.Integer)
    assert isinstance(columns["cost_usd"].type, sa.Numeric)
    assert (columns["cost_usd"].type.precision, columns["cost_usd"].type.scale) == (12, 6)
    assert str(columns["created_at"].server_default.arg) == "now()"
    assert "updated_at" not in columns

    pks = _constraints(table_args, sa.PrimaryKeyConstraint)
    assert len(pks) == 1 and pks[0].name == "pk_events"

    uniques = _constraints(table_args, sa.UniqueConstraint)
    assert uniques == []

    fks = _constraints(table_args, sa.ForeignKeyConstraint)
    fk_by_name = {fk.name: fk for fk in fks}
    assert set(fk_by_name) == {
        "fk_events_campaign_run_id_campaign_runs",
        "fk_events_actor_member_id_campaign_run_members",
    }
    assert [
        e.target_fullname for e in fk_by_name["fk_events_campaign_run_id_campaign_runs"].elements
    ] == ["campaign_runs.id"]
    assert [
        e.target_fullname
        for e in fk_by_name["fk_events_actor_member_id_campaign_run_members"].elements
    ] == ["campaign_run_members.id"]

    ondelete_by_name = {name: fk.ondelete for name, fk in fk_by_name.items()}
    assert ondelete_by_name == {
        "fk_events_campaign_run_id_campaign_runs": "CASCADE",
        "fk_events_actor_member_id_campaign_run_members": "SET NULL",
    }

    checks = _constraints(table_args, sa.CheckConstraint)
    checks_by_name = {check.name: str(check.sqltext) for check in checks}
    assert set(checks_by_name) == {"type", "visibility"}
    assert checks_by_name["type"] == (
        "type IN ('narration','player_action','roll','tool_call','error')"
    )
    assert checks_by_name["visibility"] == "visibility IN ('player','dm')"

    index_calls = recorded_calls[1:]
    assert [call[1] for call in index_calls] == [
        (
            "ix_events_campaign_run_id_visibility_id",
            "events",
            ["campaign_run_id", "visibility", "id"],
        ),
        ("ix_events_campaign_run_id_turn_id", "events", ["campaign_run_id", "turn_id"]),
    ]
    for _, _, kwargs in index_calls:
        assert kwargs == {}


def test_downgrade_reverses_upgrade_exactly(migration, recorded_calls):
    migration.downgrade()

    assert recorded_calls == [
        ("drop_index", ("ix_events_campaign_run_id_turn_id",), {"table_name": "events"}),
        ("drop_index", ("ix_events_campaign_run_id_visibility_id",), {"table_name": "events"}),
        ("drop_table", ("events",), {}),
    ]
