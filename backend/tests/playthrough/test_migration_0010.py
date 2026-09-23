"""WI1: `0010_more_event_types` -- revision chain and `upgrade()`/
`downgrade()` symmetry (sprint 010/04). Engine-free: `alembic.op` is a
module-level proxy, so its individual functions are monkeypatched with
recording stand-ins rather than ever executing against a real connection --
`run_migrations_online()` is never called, matching
`backend/tests/conftest.py`'s suite-wide ban on a real engine. Mirrors
`test_migration_0007.py`'s own pattern for its `events.type` step."""

import importlib.util
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0010_more_event_types.py"
)

OLD_EVENT_TYPE_VALUES = (
    "type IN ('narration','player_action','roll_requested','roll','question',"
    "'tool_call','scene_entered','adventure_started','adventure_completed',"
    "'system','error','warning')"
)
NEW_EVENT_TYPE_VALUES = (
    "type IN ('narration','player_action','roll_requested','roll','question',"
    "'tool_call','scene_entered','adventure_started','adventure_completed',"
    "'system','error','warning','item_moved','hp_changed','way_opened',"
    "'rule_looked_up')"
)


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("playthrough_migration_0010", MIGRATION_PATH)
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

    for name in ("drop_constraint", "create_check_constraint"):
        monkeypatch.setattr(migration.op, name, _recorder(name))

    return calls


def test_revision_is_0010(migration):
    assert migration.revision == "0010"


def test_down_revision_is_0009(migration):
    assert migration.down_revision == "0009"


def test_upgrade_widens_the_event_type_check_to_sixteen_values(migration, recorded_calls):
    migration.upgrade()

    assert [call[0] for call in recorded_calls] == ["drop_constraint", "create_check_constraint"]

    _, drop_args, drop_kwargs = recorded_calls[0]
    assert drop_args == ("type", "events")
    assert drop_kwargs == {"type_": "check"}

    _, create_args, _ = recorded_calls[1]
    assert create_args == ("type", "events", NEW_EVENT_TYPE_VALUES)


def test_downgrade_restores_the_twelve_value_check_exactly(migration, recorded_calls):
    migration.downgrade()

    assert [call[0] for call in recorded_calls] == ["drop_constraint", "create_check_constraint"]

    _, drop_args, drop_kwargs = recorded_calls[0]
    assert drop_args == ("type", "events")
    assert drop_kwargs == {"type_": "check"}

    _, create_args, _ = recorded_calls[1]
    assert create_args == ("type", "events", OLD_EVENT_TYPE_VALUES)


def test_migration_touches_nothing_0007_or_0009_owns(migration):
    source = MIGRATION_PATH.read_text()
    for symbol in (
        "campaign_runs",
        "objects",
        "ck_campaign_runs_status",
        "srd_rules",
        "uq_srd_rules_source_version",
    ):
        assert symbol not in source
