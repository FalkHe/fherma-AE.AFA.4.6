"""WI1: `CampaignRun` and `CampaignRunMember` column shape, the status/role
value sets, the one-member-per-run uniqueness and both `ON DELETE CASCADE`
foreign keys (`research.md` "Interfaces"). Engine-free -- everything here is
read off the declarative model's `Table`, never a real connection."""

from sqlalchemy import CHAR, CheckConstraint, Numeric, String, Text, UniqueConstraint
from sqlalchemy.types import DateTime

from app.modules.playthrough.models import CampaignRun, CampaignRunMember


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
