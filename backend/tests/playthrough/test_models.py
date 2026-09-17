"""WI1: `CampaignRun` and `CampaignRunMember` column shape, the status/role
value sets, the one-member-per-run uniqueness and both `ON DELETE CASCADE`
foreign keys, plus `AdventureRun`'s column shape, its two-value status set,
one row per adventure, at most one adventure in progress per run, the
finished/unfinished `completed_at` pairing and its cascade, plus
`GameObject`'s column shape, the three-value `kind` set, the four fighting
stats being present on a creature and nothing else, health staying within
its maximum, position being whole or absent, a carried thing never also
having a position, one thing per key per campaign run and no limit on how
many things a member holds, plus `Event`'s column shape and order, the
five-value `type` set and the two-value `visibility` set, `cost_usd` typed
as an exact decimal rather than a float, the cascade on `campaign_run_id`
and the clear-on-delete on `actor_member_id`, exactly two indexes with no
unique constraint, no sequence column and no `updated_at`
(`research.md` "Interfaces"). Engine-free -- everything here is read off
the declarative model's `Table`, never a real connection."""

from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime

from app.modules.playthrough.models import (
    AdventureRun,
    CampaignRun,
    CampaignRunMember,
    Event,
    GameObject,
)


def _column(model, name):
    return model.__table__.columns[name]


def _check_constraint(model, name):
    for constraint in model.__table__.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == name:
            return constraint
    raise AssertionError(f"no CheckConstraint named {name!r} on {model.__table__.name}")


def test_campaign_runs_table_name():
    assert CampaignRun.__tablename__ == "campaign_runs"


def test_campaign_run_id_is_the_shared_id_type_primary_key():
    column = _column(CampaignRun, "id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.primary_key
    assert column.default is not None


def test_campaign_run_campaign_id_is_a_non_nullable_varchar_64():
    column = _column(CampaignRun, "campaign_id")
    assert isinstance(column.type, String)
    assert column.type.length == 64
    assert column.nullable is False


def test_campaign_run_content_version_is_a_non_nullable_varchar_16():
    column = _column(CampaignRun, "content_version")
    assert isinstance(column.type, String)
    assert column.type.length == 16
    assert column.nullable is False


def test_campaign_run_title_is_a_nullable_varchar_120():
    column = _column(CampaignRun, "title")
    assert isinstance(column.type, String)
    assert column.type.length == 120
    assert column.nullable is True


def test_campaign_run_status_is_non_nullable_with_server_default_active():
    column = _column(CampaignRun, "status")
    assert isinstance(column.type, String)
    assert column.type.length == 16
    assert column.nullable is False
    assert column.server_default is not None
    assert "active" in str(column.server_default.arg)


def test_campaign_run_status_accepts_exactly_three_values():
    constraint = _check_constraint(CampaignRun, "ck_campaign_runs_status")
    assert str(constraint.sqltext) == "status IN ('active','archived','finished')"


def test_campaign_run_model_is_a_nullable_varchar_64():
    column = _column(CampaignRun, "model")
    assert isinstance(column.type, String)
    assert column.type.length == 64
    assert column.nullable is True


def test_campaign_run_temperature_is_a_nullable_numeric_3_2():
    column = _column(CampaignRun, "temperature")
    assert isinstance(column.type, Numeric)
    assert column.type.precision == 3
    assert column.type.scale == 2
    assert column.nullable is True


def test_campaign_run_personality_prompt_id_is_a_nullable_varchar_128():
    column = _column(CampaignRun, "personality_prompt_id")
    assert isinstance(column.type, String)
    assert column.type.length == 128
    assert column.nullable is True


def test_campaign_run_system_prompt_override_is_a_nullable_text_column():
    column = _column(CampaignRun, "system_prompt_override")
    assert isinstance(column.type, Text)
    assert column.nullable is True


def test_campaign_run_created_at_is_a_timezone_aware_datetime_with_server_default():
    column = _column(CampaignRun, "created_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None


def test_campaign_run_updated_at_has_a_server_default_and_a_model_side_onupdate():
    column = _column(CampaignRun, "updated_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None
    assert column.onupdate is not None


def test_campaign_run_members_table_name():
    assert CampaignRunMember.__tablename__ == "campaign_run_members"


def test_campaign_run_member_id_is_the_shared_id_type_primary_key():
    column = _column(CampaignRunMember, "id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.primary_key
    assert column.default is not None


def test_campaign_run_member_campaign_run_id_cascades_on_delete():
    column = _column(CampaignRunMember, "campaign_run_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is False
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "campaign_runs"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_campaign_run_member_user_id_cascades_on_delete_and_is_indexed():
    column = _column(CampaignRunMember, "user_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is False
    assert column.index is True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "users"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_campaign_run_member_role_is_non_nullable_with_server_default_owner():
    column = _column(CampaignRunMember, "role")
    assert isinstance(column.type, String)
    assert column.type.length == 16
    assert column.nullable is False
    assert column.server_default is not None
    assert "owner" in str(column.server_default.arg)


def test_campaign_run_member_role_accepts_exactly_one_value():
    constraint = _check_constraint(CampaignRunMember, "ck_campaign_run_members_role")
    assert str(constraint.sqltext) == "role IN ('owner')"


def test_campaign_run_member_created_at_is_a_timezone_aware_datetime_with_server_default():
    column = _column(CampaignRunMember, "created_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None


def test_campaign_run_member_allows_only_one_member_per_run():
    for constraint in CampaignRunMember.__table__.constraints:
        if (
            isinstance(constraint, UniqueConstraint)
            and constraint.name == "uq_campaign_run_members_campaign_run_id"
        ):
            assert [column.name for column in constraint.columns] == [
                "campaign_run_id",
                "user_id",
            ]
            return
    raise AssertionError("no UniqueConstraint named uq_campaign_run_members_campaign_run_id")


def _index(model, name):
    for index in model.__table__.indexes:
        if index.name == name:
            return index
    raise AssertionError(f"no Index named {name!r} on {model.__table__.name}")


def test_adventure_runs_table_name():
    assert AdventureRun.__tablename__ == "adventure_runs"


def test_adventure_run_id_is_the_shared_id_type_primary_key():
    column = _column(AdventureRun, "id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.primary_key
    assert column.default is not None


def test_adventure_run_campaign_run_id_cascades_on_delete_and_is_not_indexed():
    column = _column(AdventureRun, "campaign_run_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is False
    assert column.index is not True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "campaign_runs"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_adventure_run_adventure_id_is_a_non_nullable_varchar_64_with_no_fk():
    column = _column(AdventureRun, "adventure_id")
    assert isinstance(column.type, String)
    assert column.type.length == 64
    assert column.nullable is False
    assert not column.foreign_keys


def test_adventure_run_status_is_non_nullable_with_server_default_active():
    column = _column(AdventureRun, "status")
    assert isinstance(column.type, String)
    assert column.type.length == 16
    assert column.nullable is False
    assert column.server_default is not None
    assert "active" in str(column.server_default.arg)


def test_adventure_run_status_accepts_exactly_two_values():
    constraint = _check_constraint(AdventureRun, "ck_adventure_runs_status")
    assert str(constraint.sqltext) == "status IN ('active','completed')"


def test_adventure_run_started_at_is_a_timezone_aware_datetime_with_server_default():
    column = _column(AdventureRun, "started_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None


def test_adventure_run_completed_at_is_a_nullable_datetime_with_no_default():
    column = _column(AdventureRun, "completed_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is True
    assert column.server_default is None
    assert column.default is None


def test_adventure_run_updated_at_has_a_server_default_and_a_model_side_onupdate():
    column = _column(AdventureRun, "updated_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None
    assert column.onupdate is not None


def test_adventure_run_allows_only_one_row_per_campaign_run_and_adventure():
    for constraint in AdventureRun.__table__.constraints:
        if (
            isinstance(constraint, UniqueConstraint)
            and constraint.name == "uq_adventure_runs_campaign_run_id"
        ):
            assert [column.name for column in constraint.columns] == [
                "campaign_run_id",
                "adventure_id",
            ]
            return
    raise AssertionError("no UniqueConstraint named uq_adventure_runs_campaign_run_id")


def test_adventure_run_allows_only_one_active_adventure_per_campaign_run():
    index = _index(AdventureRun, "uq_adventure_runs_active")
    assert isinstance(index, Index)
    assert index.unique is True
    assert [column.name for column in index.columns] == ["campaign_run_id"]
    where = index.dialect_options["postgresql"]["where"]
    assert str(where) == "status = 'active'"


def test_adventure_run_completed_at_is_set_exactly_when_status_is_completed():
    constraint = _check_constraint(AdventureRun, "ck_adventure_runs_completed_at")
    assert str(constraint.sqltext) == "(status = 'completed') = (completed_at IS NOT NULL)"


def test_objects_table_name():
    assert GameObject.__tablename__ == "objects"


def test_object_id_is_the_shared_id_type_primary_key():
    column = _column(GameObject, "id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.primary_key
    assert column.default is not None


def test_object_campaign_run_id_cascades_on_delete_and_is_indexed():
    column = _column(GameObject, "campaign_run_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is False
    assert column.index is True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "campaign_runs"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_object_member_id_is_nullable_cascades_on_delete_and_is_indexed():
    column = _column(GameObject, "member_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is True
    assert column.index is True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "campaign_run_members"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_object_member_id_has_no_unique_constraint_so_a_member_may_hold_many_things():
    for constraint in GameObject.__table__.constraints:
        if isinstance(constraint, UniqueConstraint):
            assert [column.name for column in constraint.columns] != ["member_id"]
    for index in GameObject.__table__.indexes:
        assert not (index.unique and [column.name for column in index.columns] == ["member_id"])


def test_object_kind_is_a_non_nullable_varchar_16_with_no_default():
    column = _column(GameObject, "kind")
    assert isinstance(column.type, String)
    assert column.type.length == 16
    assert column.nullable is False
    assert column.default is None
    assert column.server_default is None


def test_object_kind_accepts_exactly_three_values():
    constraint = _check_constraint(GameObject, "ck_objects_kind")
    assert str(constraint.sqltext) == "kind IN ('creature','item','fixture')"


def test_object_template_id_is_a_non_nullable_varchar_64_with_no_fk():
    column = _column(GameObject, "template_id")
    assert isinstance(column.type, String)
    assert column.type.length == 64
    assert column.nullable is False
    assert not column.foreign_keys


def test_object_instance_key_is_a_non_nullable_varchar_160():
    column = _column(GameObject, "instance_key")
    assert isinstance(column.type, String)
    assert column.type.length == 160
    assert column.nullable is False


def test_object_name_is_a_non_nullable_varchar_120():
    column = _column(GameObject, "name")
    assert isinstance(column.type, String)
    assert column.type.length == 120
    assert column.nullable is False


def test_object_source_adventure_id_is_a_nullable_varchar_64_with_no_fk():
    column = _column(GameObject, "source_adventure_id")
    assert isinstance(column.type, String)
    assert column.type.length == 64
    assert column.nullable is True
    assert not column.foreign_keys


def test_object_source_scene_id_is_a_nullable_varchar_64_with_no_fk():
    column = _column(GameObject, "source_scene_id")
    assert isinstance(column.type, String)
    assert column.type.length == 64
    assert column.nullable is True
    assert not column.foreign_keys


def test_object_adventure_run_id_is_nullable_sets_null_on_delete_and_is_not_indexed():
    column = _column(GameObject, "adventure_run_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is True
    assert column.index is not True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "adventure_runs"
    assert fk.column.name == "id"
    assert fk.ondelete == "SET NULL"


def test_object_scene_id_is_a_nullable_varchar_64():
    column = _column(GameObject, "scene_id")
    assert isinstance(column.type, String)
    assert column.type.length == 64
    assert column.nullable is True


def test_object_owner_object_id_is_nullable_self_fk_cascades_on_delete_and_is_indexed():
    column = _column(GameObject, "owner_object_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is True
    assert column.index is True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "objects"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_object_current_hp_is_a_nullable_integer():
    column = _column(GameObject, "current_hp")
    assert isinstance(column.type, Integer)
    assert column.nullable is True


def test_object_max_hp_is_a_nullable_integer():
    column = _column(GameObject, "max_hp")
    assert isinstance(column.type, Integer)
    assert column.nullable is True


def test_object_armour_class_is_a_nullable_integer():
    column = _column(GameObject, "armour_class")
    assert isinstance(column.type, Integer)
    assert column.nullable is True


def test_object_is_alive_is_a_nullable_boolean_with_no_default():
    column = _column(GameObject, "is_alive")
    assert isinstance(column.type, Boolean)
    assert column.nullable is True
    assert column.default is None
    assert column.server_default is None


def test_object_the_four_fighting_stats_are_present_on_a_creature_and_nothing_else():
    constraint = _check_constraint(GameObject, "ck_objects_stats_creature_only")
    assert str(constraint.sqltext) == (
        "(kind = 'creature') = (current_hp IS NOT NULL) AND "
        "(kind = 'creature') = (max_hp IS NOT NULL) AND "
        "(kind = 'creature') = (armour_class IS NOT NULL) AND "
        "(kind = 'creature') = (is_alive IS NOT NULL)"
    )


def test_object_health_stays_within_its_maximum():
    constraint = _check_constraint(GameObject, "ck_objects_hp_range")
    assert str(constraint.sqltext) == (
        "(current_hp IS NULL AND max_hp IS NULL) OR "
        "(current_hp IS NOT NULL AND max_hp IS NOT NULL AND "
        "current_hp >= 0 AND current_hp <= max_hp)"
    )


def test_object_state_is_a_non_nullable_jsonb_column_defaulting_to_an_empty_object():
    column = _column(GameObject, "state")
    assert isinstance(column.type, JSONB)
    assert column.nullable is False
    assert column.server_default is not None
    assert "{}" in str(column.server_default.arg)


def test_object_created_at_is_a_timezone_aware_datetime_with_server_default():
    column = _column(GameObject, "created_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None


def test_object_updated_at_has_a_server_default_and_a_model_side_onupdate():
    column = _column(GameObject, "updated_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None
    assert column.onupdate is not None


def test_object_allows_one_thing_per_key_per_campaign_run():
    for constraint in GameObject.__table__.constraints:
        if (
            isinstance(constraint, UniqueConstraint)
            and constraint.name == "uq_objects_campaign_run_id"
        ):
            assert [column.name for column in constraint.columns] == [
                "campaign_run_id",
                "instance_key",
            ]
            return
    raise AssertionError("no UniqueConstraint named uq_objects_campaign_run_id")


def test_object_position_is_whole_or_absent():
    constraint = _check_constraint(GameObject, "ck_objects_position")
    assert str(constraint.sqltext) == "(adventure_run_id IS NULL) = (scene_id IS NULL)"


def test_object_a_carried_thing_has_no_position():
    constraint = _check_constraint(GameObject, "ck_objects_carried")
    assert str(constraint.sqltext) == (
        "owner_object_id IS NULL OR (adventure_run_id IS NULL AND scene_id IS NULL)"
    )


def test_object_position_columns_are_indexed_together():
    index = _index(GameObject, "ix_objects_adventure_run_id_scene_id")
    assert isinstance(index, Index)
    assert [column.name for column in index.columns] == ["adventure_run_id", "scene_id"]


def test_objects_has_no_orm_relationship():
    assert GameObject.__mapper__.relationships.keys() == []


def test_events_table_name():
    assert Event.__tablename__ == "events"


def test_events_primary_key_is_named_pk_events():
    assert Event.__table__.primary_key.name == "pk_events"


def test_events_column_order_has_no_sequence_column():
    assert [column.name for column in Event.__table__.columns] == [
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
    ]


def test_event_id_is_the_shared_id_type_primary_key():
    column = _column(Event, "id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.primary_key
    assert column.default is not None


def test_event_campaign_run_id_is_non_nullable_and_cascades_on_delete():
    column = _column(Event, "campaign_run_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is False
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "campaign_runs"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE"


def test_event_actor_member_id_is_nullable_and_cleared_on_delete():
    column = _column(Event, "actor_member_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is True
    (fk,) = column.foreign_keys
    assert fk.column.table.name == "campaign_run_members"
    assert fk.column.name == "id"
    assert fk.ondelete == "SET NULL"


def test_event_turn_id_is_a_nullable_shared_id_type_with_no_fk():
    column = _column(Event, "turn_id")
    assert isinstance(column.type, CHAR)
    assert column.type.length == 26
    assert column.nullable is True
    assert not column.foreign_keys


def test_event_type_is_a_non_nullable_varchar_32_with_no_default():
    column = _column(Event, "type")
    assert isinstance(column.type, String)
    assert column.type.length == 32
    assert column.nullable is False
    assert column.default is None
    assert column.server_default is None


def test_event_type_accepts_exactly_five_values():
    constraint = _check_constraint(Event, "ck_events_type")
    assert str(constraint.sqltext) == (
        "type IN ('narration','player_action','roll','tool_call','error')"
    )


def test_event_visibility_is_a_non_nullable_varchar_8_with_no_default():
    column = _column(Event, "visibility")
    assert isinstance(column.type, String)
    assert column.type.length == 8
    assert column.nullable is False
    assert column.default is None
    assert column.server_default is None


def test_event_visibility_accepts_exactly_two_values():
    constraint = _check_constraint(Event, "ck_events_visibility")
    assert str(constraint.sqltext) == "visibility IN ('player','dm')"


def test_event_payload_is_a_non_nullable_jsonb_column_with_no_default():
    column = _column(Event, "payload")
    assert isinstance(column.type, JSONB)
    assert column.nullable is False
    assert column.default is None
    assert column.server_default is None


def test_event_prompt_tokens_is_a_nullable_integer():
    column = _column(Event, "prompt_tokens")
    assert isinstance(column.type, Integer)
    assert column.nullable is True


def test_event_completion_tokens_is_a_nullable_integer():
    column = _column(Event, "completion_tokens")
    assert isinstance(column.type, Integer)
    assert column.nullable is True


def test_event_cost_usd_is_a_nullable_exact_decimal_never_a_float():
    column = _column(Event, "cost_usd")
    assert isinstance(column.type, Numeric)
    assert column.type.precision == 12
    assert column.type.scale == 6
    assert column.nullable is True
    assert column.type.asdecimal is True
    assert column.type.python_type is Decimal


def test_event_created_at_is_a_timezone_aware_datetime_with_server_default_and_no_onupdate():
    column = _column(Event, "created_at")
    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.server_default is not None
    assert column.onupdate is None


def test_events_has_no_updated_at_column():
    assert "updated_at" not in Event.__table__.columns


def test_events_has_exactly_two_indexes():
    assert {index.name for index in Event.__table__.indexes} == {
        "ix_events_campaign_run_id_visibility_id",
        "ix_events_campaign_run_id_turn_id",
    }


def test_event_campaign_run_id_visibility_id_index_column_order():
    index = _index(Event, "ix_events_campaign_run_id_visibility_id")
    assert [column.name for column in index.columns] == [
        "campaign_run_id",
        "visibility",
        "id",
    ]


def test_event_campaign_run_id_turn_id_index_column_order():
    index = _index(Event, "ix_events_campaign_run_id_turn_id")
    assert [column.name for column in index.columns] == ["campaign_run_id", "turn_id"]


def test_events_has_no_unique_constraint():
    for constraint in Event.__table__.constraints:
        assert not isinstance(constraint, UniqueConstraint)


def test_events_has_no_orm_relationship():
    assert Event.__mapper__.relationships.keys() == []
