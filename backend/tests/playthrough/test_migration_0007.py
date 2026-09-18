"""WI1: `0007_lifecycle_and_event_types` -- revision chain and
`upgrade()`/`downgrade()` symmetry (AC1, AC2, AC3, AC4). Engine-free:
`alembic.op` is a module-level proxy, so its individual functions are
monkeypatched with recording stand-ins rather than ever executing against a
real connection -- `run_migrations_online()` is never called, matching
`backend/tests/conftest.py`'s suite-wide ban on a real engine."""

import importlib.util
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0007_lifecycle_and_event_types.py"
)

NEW_STATUS_VALUES = "status IN ('setup','ready','active','archived','finished')"
OLD_STATUS_VALUES = "status IN ('active','archived','finished')"
NEW_EVENT_TYPE_VALUES = (
    "type IN ('narration','player_action','roll_requested','roll','question',"
    "'tool_call','scene_entered','adventure_started','adventure_completed',"
    "'system','error','warning')"
)
OLD_EVENT_TYPE_VALUES = "type IN ('narration','player_action','roll','tool_call','error')"


@pytest.fixture
def migration():
    spec = importlib.util.spec_from_file_location("playthrough_migration_0007", MIGRATION_PATH)
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

    for name in ("drop_constraint", "create_check_constraint", "alter_column"):
        monkeypatch.setattr(migration.op, name, _recorder(name))

    return calls


def test_revision_is_0007(migration):
    assert migration.revision == "0007"


def test_down_revision_is_0006(migration):
    assert migration.down_revision == "0006"


def test_upgrade_widens_status_drops_template_id_not_null_and_widens_event_type(
    migration, recorded_calls
):
    migration.upgrade()

    assert [call[0] for call in recorded_calls] == [
        "drop_constraint",
        "create_check_constraint",
        "alter_column",
        "alter_column",
        "drop_constraint",
        "create_check_constraint",
    ]

    _, drop_status_args, drop_status_kwargs = recorded_calls[0]
    assert drop_status_args == ("status", "campaign_runs")
    assert drop_status_kwargs == {"type_": "check"}

    _, create_status_args, _ = recorded_calls[1]
    assert create_status_args == ("status", "campaign_runs", NEW_STATUS_VALUES)

    _, status_default_args, status_default_kwargs = recorded_calls[2]
    assert status_default_args == ("campaign_runs", "status")
    assert status_default_kwargs["server_default"] == "setup"
    assert status_default_kwargs["existing_nullable"] is False

    _, template_id_args, template_id_kwargs = recorded_calls[3]
    assert template_id_args == ("objects", "template_id")
    assert template_id_kwargs["nullable"] is True

    _, drop_type_args, drop_type_kwargs = recorded_calls[4]
    assert drop_type_args == ("type", "events")
    assert drop_type_kwargs == {"type_": "check"}

    _, create_type_args, _ = recorded_calls[5]
    assert create_type_args == ("type", "events", NEW_EVENT_TYPE_VALUES)


def test_downgrade_restores_the_prior_checks_default_and_not_null_exactly(
    migration, recorded_calls
):
    migration.downgrade()

    assert [call[0] for call in recorded_calls] == [
        "drop_constraint",
        "create_check_constraint",
        "alter_column",
        "alter_column",
        "drop_constraint",
        "create_check_constraint",
    ]

    _, drop_type_args, drop_type_kwargs = recorded_calls[0]
    assert drop_type_args == ("type", "events")
    assert drop_type_kwargs == {"type_": "check"}

    _, create_type_args, _ = recorded_calls[1]
    assert create_type_args == ("type", "events", OLD_EVENT_TYPE_VALUES)

    _, template_id_args, template_id_kwargs = recorded_calls[2]
    assert template_id_args == ("objects", "template_id")
    assert template_id_kwargs["nullable"] is False

    _, status_default_args, status_default_kwargs = recorded_calls[3]
    assert status_default_args == ("campaign_runs", "status")
    assert status_default_kwargs["server_default"] == "active"

    _, drop_status_args, drop_status_kwargs = recorded_calls[4]
    assert drop_status_args == ("status", "campaign_runs")
    assert drop_status_kwargs == {"type_": "check"}

    _, create_status_args, _ = recorded_calls[5]
    assert create_status_args == ("status", "campaign_runs", OLD_STATUS_VALUES)


def test_downgrade_docstring_names_the_template_id_not_null_risk(migration):
    assert "template_id" in migration.__doc__
    assert "NOT NULL" in migration.__doc__
