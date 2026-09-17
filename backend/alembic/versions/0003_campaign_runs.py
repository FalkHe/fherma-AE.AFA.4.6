"""playthrough: campaign_runs and campaign_run_members tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

ID_TYPE = sa.CHAR(26)

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaign_runs",
        sa.Column("id", ID_TYPE, nullable=False),
        sa.Column("campaign_id", sa.String(length=64), nullable=False),
        sa.Column("content_version", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=True),
        sa.Column("personality_prompt_id", sa.String(length=128), nullable=True),
        sa.Column("system_prompt_override", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_runs"),
        sa.CheckConstraint("status IN ('active','archived','finished')", name="status"),
    )

    op.create_table(
        "campaign_run_members",
        sa.Column("id", ID_TYPE, nullable=False),
        sa.Column("campaign_run_id", ID_TYPE, nullable=False),
        sa.Column("user_id", ID_TYPE, nullable=False),
        sa.Column(
            "role",
            sa.String(length=16),
            server_default="owner",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_run_members"),
        sa.UniqueConstraint(
            "campaign_run_id", "user_id", name="uq_campaign_run_members_campaign_run_id"
        ),
        sa.ForeignKeyConstraint(
            ["campaign_run_id"],
            ["campaign_runs.id"],
            name="fk_campaign_run_members_campaign_run_id_campaign_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_campaign_run_members_user_id_users",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role IN ('owner')", name="role"),
    )
    op.create_index("ix_campaign_run_members_user_id", "campaign_run_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_run_members_user_id", table_name="campaign_run_members")
    op.drop_table("campaign_run_members")
    op.drop_table("campaign_runs")
