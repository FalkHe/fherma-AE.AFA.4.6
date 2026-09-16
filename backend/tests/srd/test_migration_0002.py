"""WI1: `0002_srd_rules` -- revision chain and `upgrade()`/`downgrade()`
symmetry (AC2). Engine-free: `alembic.op` is a module-level proxy, so its
individual functions are monkeypatched with recording stand-ins rather than
ever executing against a real connection -- `run_migrations_online()` is
never called, matching `backend/tests/conftest.py`'s suite-wide ban on a real
engine."""

import importlib.util
from pathlib import Path

import pytest

MIGRATION_PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0002_srd_rules.py"


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("srd_migration_0002", MIGRATION_PATH)
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

    for name in ("execute", "create_table", "create_index", "drop_index", "drop_table"):
        monkeypatch.setattr(migration.op, name, _recorder(name))

    return calls


def test_revision_is_0002(migration):
    assert migration.revision == "0002"


def test_down_revision_is_0001(migration):
    assert migration.down_revision == "0001"


def test_upgrade_creates_the_extension_before_the_table_and_index(migration, recorded_calls):
    migration.upgrade()

    names = [call[0] for call in recorded_calls]
    assert names == ["execute", "create_table", "create_index"]

    _, execute_args, _ = recorded_calls[0]
    assert execute_args[0] == "CREATE EXTENSION IF NOT EXISTS vector"

    _, table_args, _ = recorded_calls[1]
    assert table_args[0] == "srd_rules"

    _, index_args, index_kwargs = recorded_calls[2]
    assert index_args[:2] == ("ix_srd_rules_embedding", "srd_rules")
    assert index_kwargs["postgresql_using"] == "hnsw"
    assert index_kwargs["postgresql_ops"] == {"embedding": "vector_cosine_ops"}


def test_downgrade_drops_the_index_then_the_table_and_leaves_the_extension(
    migration, recorded_calls
):
    migration.downgrade()

    assert recorded_calls == [
        ("drop_index", ("ix_srd_rules_embedding",), {"table_name": "srd_rules"}),
        ("drop_table", ("srd_rules",), {}),
    ]
