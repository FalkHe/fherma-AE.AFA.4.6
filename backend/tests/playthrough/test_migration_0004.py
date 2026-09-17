"""WI2: `0004_adventure_runs` -- revision chain and `upgrade()`/`downgrade()`
symmetry (AC1, AC5). Engine-free: `alembic.op` is a module-level proxy, so
its individual functions are monkeypatched with recording stand-ins rather
than ever executing against a real connection -- `run_migrations_online()`
is never called, matching `backend/tests/conftest.py`'s suite-wide ban on a
real engine."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0004_adventure_runs.py"
)


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("playthrough_migration_0004", MIGRATION_PATH)
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


def test_revision_is_0004(migration):
    assert migration.revision == "0004"


def test_down_revision_is_0003(migration):
    assert migration.down_revision == "0003"


def test_upgrade_creates_adventure_runs_then_the_index(migration, recorded_calls):
    migration.upgrade()

    assert [call[0] for call in recorded_calls] == ["create_table", "create_index"]

    _, run_args, _ = recorded_calls[0]
    assert run_args[0] == "adventure_runs"
    columns = _columns(run_args)
    assert set(columns) == {
        "id",
        "campaign_run_id",
        "adventure_id",
        "status",
        "started_at",
        "completed_at",
        "updated_at",
    }
    not_null = {
        "id",
        "campaign_run_id",
        "adventure_id",
        "status",
        "started_at",
        "updated_at",
    }
    for name, column in columns.items():
        assert column.nullable == (name not in not_null), name

    assert str(columns["status"].server_default.arg) == "active"
    assert columns["updated_at"].onupdate is None

    pks = _constraints(run_args, sa.PrimaryKeyConstraint)
    assert len(pks) == 1 and pks[0].name == "pk_adventure_runs"

    uniques = _constraints(run_args, sa.UniqueConstraint)
    assert len(uniques) == 1
    assert uniques[0].name == "uq_adventure_runs_campaign_run_id"
    # Unattached (never fed to a real `Table`), so column names live in
    # `_pending_colargs`, not the resolved `.columns` collection.
    assert uniques[0]._pending_colargs == ["campaign_run_id", "adventure_id"]

    fks = _constraints(run_args, sa.ForeignKeyConstraint)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.name == "fk_adventure_runs_campaign_run_id_campaign_runs"
    assert fk.ondelete == "CASCADE"
    # Unattached constraints never resolve `.column`, so read the raw
    # "table.column" target string instead.
    assert [e.target_fullname for e in fk.elements] == ["campaign_runs.id"]

    checks = _constraints(run_args, sa.CheckConstraint)
    checks_by_name = {check.name: check for check in checks}
    assert set(checks_by_name) == {"status", "completed_at"}
    status_sql = str(checks_by_name["status"].sqltext)
    assert "active" in status_sql and "completed" in status_sql
    completed_at_sql = str(checks_by_name["completed_at"].sqltext)
    assert "completed_at" in completed_at_sql and "status" in completed_at_sql

    _, index_args, index_kwargs = recorded_calls[1]
    assert index_args == ("uq_adventure_runs_active", "adventure_runs", ["campaign_run_id"])
    assert index_kwargs["unique"] is True
    assert "status = 'active'" in str(index_kwargs["postgresql_where"])


def test_downgrade_reverses_upgrade_exactly(migration, recorded_calls):
    migration.downgrade()

    assert recorded_calls == [
        (
            "drop_index",
            ("uq_adventure_runs_active",),
            {"table_name": "adventure_runs"},
        ),
        ("drop_table", ("adventure_runs",), {}),
    ]
