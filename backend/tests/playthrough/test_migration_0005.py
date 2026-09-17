"""WI2: `0005_objects` -- revision chain, the exact shape of the `objects`
table (AC1, AC5) and `upgrade()`/`downgrade()` symmetry. Engine-free:
`alembic.op` is a module-level proxy, so its individual functions are
monkeypatched with recording stand-ins rather than ever executing against a
real connection -- `run_migrations_online()` is never called, matching
`backend/tests/conftest.py`'s suite-wide ban on a real engine."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

MIGRATION_PATH = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0005_objects.py"


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("playthrough_migration_0005", MIGRATION_PATH)
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


def test_revision_is_0005(migration):
    assert migration.revision == "0005"


def test_down_revision_is_0004(migration):
    assert migration.down_revision == "0004"


def test_upgrade_creates_objects_then_its_four_indexes(migration, recorded_calls):
    migration.upgrade()

    assert [call[0] for call in recorded_calls] == [
        "create_table",
        "create_index",
        "create_index",
        "create_index",
        "create_index",
    ]

    _, table_args, _ = recorded_calls[0]
    assert table_args[0] == "objects"
    columns = _columns(table_args)
    assert set(columns) == {
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
    not_null = {
        "id",
        "campaign_run_id",
        "kind",
        "template_id",
        "instance_key",
        "name",
        "state",
        "created_at",
        "updated_at",
    }
    for name, column in columns.items():
        assert column.nullable == (name not in not_null), name

    # The two provenance columns are distinct from the two position columns:
    # different names, and provenance carries no FK while position does.
    assert {"source_adventure_id", "source_scene_id"}.isdisjoint({"adventure_run_id", "scene_id"})

    assert str(columns["state"].server_default.arg) == "'{}'::jsonb"
    assert isinstance(columns["state"].type, JSONB)
    assert columns["updated_at"].onupdate is None

    pks = _constraints(table_args, sa.PrimaryKeyConstraint)
    assert len(pks) == 1 and pks[0].name == "pk_objects"

    uniques = _constraints(table_args, sa.UniqueConstraint)
    assert len(uniques) == 1
    assert uniques[0].name == "uq_objects_campaign_run_id"
    # Unattached (never fed to a real `Table`), so column names live in
    # `_pending_colargs`, not the resolved `.columns` collection.
    assert uniques[0]._pending_colargs == ["campaign_run_id", "instance_key"]

    fks = _constraints(table_args, sa.ForeignKeyConstraint)
    fk_by_name = {fk.name: fk for fk in fks}
    assert set(fk_by_name) == {
        "fk_objects_campaign_run_id_campaign_runs",
        "fk_objects_member_id_campaign_run_members",
        "fk_objects_adventure_run_id_adventure_runs",
        "fk_objects_owner_object_id_objects",
    }
    # Unattached constraints never resolve `.column`, so read the raw
    # "table.column" target string instead.
    assert [
        e.target_fullname for e in fk_by_name["fk_objects_campaign_run_id_campaign_runs"].elements
    ] == ["campaign_runs.id"]
    assert [
        e.target_fullname for e in fk_by_name["fk_objects_member_id_campaign_run_members"].elements
    ] == ["campaign_run_members.id"]
    assert [
        e.target_fullname for e in fk_by_name["fk_objects_adventure_run_id_adventure_runs"].elements
    ] == ["adventure_runs.id"]
    assert [
        e.target_fullname for e in fk_by_name["fk_objects_owner_object_id_objects"].elements
    ] == ["objects.id"]

    ondelete_by_name = {name: fk.ondelete for name, fk in fk_by_name.items()}
    assert ondelete_by_name == {
        "fk_objects_campaign_run_id_campaign_runs": "CASCADE",
        "fk_objects_member_id_campaign_run_members": "CASCADE",
        "fk_objects_adventure_run_id_adventure_runs": "SET NULL",
        "fk_objects_owner_object_id_objects": "CASCADE",
    }

    checks = _constraints(table_args, sa.CheckConstraint)
    checks_by_name = {check.name: str(check.sqltext) for check in checks}
    assert set(checks_by_name) == {
        "kind",
        "stats_creature_only",
        "hp_range",
        "position",
        "carried",
    }
    assert checks_by_name["kind"] == "kind IN ('creature','item','fixture')"
    assert checks_by_name["stats_creature_only"] == (
        "(kind = 'creature') = (current_hp IS NOT NULL) AND "
        "(kind = 'creature') = (max_hp IS NOT NULL) AND "
        "(kind = 'creature') = (armour_class IS NOT NULL) AND "
        "(kind = 'creature') = (is_alive IS NOT NULL)"
    )
    assert checks_by_name["hp_range"] == (
        "(current_hp IS NULL AND max_hp IS NULL) OR "
        "(current_hp IS NOT NULL AND max_hp IS NOT NULL AND "
        "current_hp >= 0 AND current_hp <= max_hp)"
    )
    assert checks_by_name["position"] == "(adventure_run_id IS NULL) = (scene_id IS NULL)"
    assert checks_by_name["carried"] == (
        "owner_object_id IS NULL OR (adventure_run_id IS NULL AND scene_id IS NULL)"
    )

    index_calls = recorded_calls[1:]
    assert [call[1] for call in index_calls] == [
        ("ix_objects_campaign_run_id", "objects", ["campaign_run_id"]),
        ("ix_objects_member_id", "objects", ["member_id"]),
        ("ix_objects_owner_object_id", "objects", ["owner_object_id"]),
        ("ix_objects_adventure_run_id_scene_id", "objects", ["adventure_run_id", "scene_id"]),
    ]
    for _, _, kwargs in index_calls:
        assert kwargs == {}


def test_downgrade_reverses_upgrade_exactly(migration, recorded_calls):
    migration.downgrade()

    assert recorded_calls == [
        ("drop_index", ("ix_objects_adventure_run_id_scene_id",), {"table_name": "objects"}),
        ("drop_index", ("ix_objects_owner_object_id",), {"table_name": "objects"}),
        ("drop_index", ("ix_objects_member_id",), {"table_name": "objects"}),
        ("drop_index", ("ix_objects_campaign_run_id",), {"table_name": "objects"}),
        ("drop_table", ("objects",), {}),
    ]
