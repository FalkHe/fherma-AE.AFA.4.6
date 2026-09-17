"""WI2: `0003_campaign_runs` -- revision chain and `upgrade()`/`downgrade()`
symmetry (AC1, AC4). Engine-free: `alembic.op` is a module-level proxy, so
its individual functions are monkeypatched with recording stand-ins rather
than ever executing against a real connection -- `run_migrations_online()`
is never called, matching `backend/tests/conftest.py`'s suite-wide ban on a
real engine."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0003_campaign_runs.py"
)


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("playthrough_migration_0003", MIGRATION_PATH)
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


def test_revision_is_0003(migration):
    assert migration.revision == "0003"


def test_down_revision_is_0002(migration):
    assert migration.down_revision == "0002"


def test_upgrade_creates_campaign_runs_then_members_then_the_index(migration, recorded_calls):
    migration.upgrade()

    assert [call[0] for call in recorded_calls] == ["create_table", "create_table", "create_index"]

    _, run_args, _ = recorded_calls[0]
    assert run_args[0] == "campaign_runs"
    columns = _columns(run_args)
    assert set(columns) == {
        "id",
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
    not_null = {
        "id",
        "campaign_id",
        "content_version",
        "status",
        "created_at",
        "updated_at",
    }
    for name, column in columns.items():
        assert column.nullable == (name not in not_null), name

    assert str(columns["status"].server_default.arg) == "active"
    assert columns["updated_at"].onupdate is None

    pks = _constraints(run_args, sa.PrimaryKeyConstraint)
    assert len(pks) == 1 and pks[0].name == "pk_campaign_runs"

    checks = _constraints(run_args, sa.CheckConstraint)
    assert len(checks) == 1
    assert checks[0].name == "status"
    sqltext = str(checks[0].sqltext)
    assert "active" in sqltext and "archived" in sqltext and "finished" in sqltext

    _, member_args, _ = recorded_calls[1]
    assert member_args[0] == "campaign_run_members"
    member_columns = _columns(member_args)
    assert set(member_columns) == {
        "id",
        "campaign_run_id",
        "user_id",
        "role",
        "created_at",
    }
    for column in member_columns.values():
        assert not column.nullable
    assert str(member_columns["role"].server_default.arg) == "owner"

    member_pks = _constraints(member_args, sa.PrimaryKeyConstraint)
    assert len(member_pks) == 1 and member_pks[0].name == "pk_campaign_run_members"

    uniques = _constraints(member_args, sa.UniqueConstraint)
    assert len(uniques) == 1
    assert uniques[0].name == "uq_campaign_run_members_campaign_run_id"
    assert [col.name for col in uniques[0].columns] == ["campaign_run_id", "user_id"]

    fks = _constraints(member_args, sa.ForeignKeyConstraint)
    fk_by_name = {fk.name: fk for fk in fks}
    assert set(fk_by_name) == {
        "fk_campaign_run_members_campaign_run_id_campaign_runs",
        "fk_campaign_run_members_user_id_users",
    }
    for fk in fks:
        assert fk.ondelete == "CASCADE"
    assert [e.column.table.name for e in fk_by_name[
        "fk_campaign_run_members_campaign_run_id_campaign_runs"
    ].elements] == ["campaign_runs"]
    assert [e.column.table.name for e in fk_by_name[
        "fk_campaign_run_members_user_id_users"
    ].elements] == ["users"]

    member_checks = _constraints(member_args, sa.CheckConstraint)
    assert len(member_checks) == 1
    assert member_checks[0].name == "role"
    assert "owner" in str(member_checks[0].sqltext)

    _, index_args, index_kwargs = recorded_calls[2]
    assert index_args == ("ix_campaign_run_members_user_id", "campaign_run_members", ["user_id"])
    assert index_kwargs == {}


def test_downgrade_reverses_upgrade_exactly(migration, recorded_calls):
    migration.downgrade()

    assert recorded_calls == [
        (
            "drop_index",
            ("ix_campaign_run_members_user_id",),
            {"table_name": "campaign_run_members"},
        ),
        ("drop_table", ("campaign_run_members",), {}),
        ("drop_table", ("campaign_runs",), {}),
    ]
