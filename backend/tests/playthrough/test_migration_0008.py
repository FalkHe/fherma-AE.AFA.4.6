"""WI1: `0008_event_embeddings` -- revision chain and
`upgrade()`/`downgrade()` symmetry (AC1). Engine-free: `alembic.op` is a
module-level proxy, so its individual functions are monkeypatched with
recording stand-ins rather than ever executing against a real connection --
`run_migrations_online()` is never called, matching
`backend/tests/conftest.py`'s suite-wide ban on a real engine."""

import importlib.util
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0008_event_embeddings.py"
)

INDEX_WHERE = "type = 'narration' AND embedding IS NOT NULL"


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("playthrough_migration_0008", MIGRATION_PATH)
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

    for name in ("add_column", "create_index", "drop_index", "drop_column"):
        monkeypatch.setattr(migration.op, name, _recorder(name))

    return calls


def test_revision_is_0008(migration):
    assert migration.revision == "0008"


def test_down_revision_is_0007(migration):
    assert migration.down_revision == "0007"


def test_upgrade_adds_both_columns_before_the_partial_index(migration, recorded_calls):
    migration.upgrade()

    assert [call[0] for call in recorded_calls] == ["add_column", "add_column", "create_index"]

    _, embedding_args, _ = recorded_calls[0]
    assert embedding_args[0] == "events"
    assert embedding_args[1].name == "embedding"
    assert embedding_args[1].nullable is True

    _, embedding_model_args, _ = recorded_calls[1]
    assert embedding_model_args[0] == "events"
    assert embedding_model_args[1].name == "embedding_model"
    assert embedding_model_args[1].nullable is True

    _, index_args, index_kwargs = recorded_calls[2]
    assert index_args == ("ix_events_embedding_narration", "events", ["embedding"])
    assert index_kwargs["postgresql_using"] == "hnsw"
    assert index_kwargs["postgresql_ops"] == {"embedding": "vector_cosine_ops"}
    assert str(index_kwargs["postgresql_where"]) == INDEX_WHERE


def test_downgrade_drops_the_index_then_both_columns(migration, recorded_calls):
    migration.downgrade()

    assert recorded_calls == [
        ("drop_index", ("ix_events_embedding_narration",), {"table_name": "events"}),
        ("drop_column", ("events", "embedding_model"), {}),
        ("drop_column", ("events", "embedding"), {}),
    ]


def test_migration_touches_nothing_0007_owns(migration):
    source = MIGRATION_PATH.read_text()
    for symbol in ("campaign_runs", "objects", "ck_campaign_runs_status", "ck_events_type"):
        assert symbol not in source
