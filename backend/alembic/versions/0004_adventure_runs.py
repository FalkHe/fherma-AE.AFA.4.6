"""playthrough: adventure_runs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

ID_TYPE = sa.CHAR(26)

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adventure_runs",
        sa.Column("id", ID_TYPE, nullable=False),
        sa.Column("campaign_run_id", ID_TYPE, nullable=False),
        sa.Column("adventure_id", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_adventure_runs"),
        sa.ForeignKeyConstraint(
            ["campaign_run_id"],
            ["campaign_runs.id"],
            name="fk_adventure_runs_campaign_run_id_campaign_runs",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "campaign_run_id", "adventure_id", name="uq_adventure_runs_campaign_run_id"
        ),
        sa.CheckConstraint("status IN ('active','completed')", name="status"),
        sa.CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at"
        ),
    )
    op.create_index(
        "uq_adventure_runs_active",
        "adventure_runs",
        ["campaign_run_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("uq_adventure_runs_active", table_name="adventure_runs")
    op.drop_table("adventure_runs")
