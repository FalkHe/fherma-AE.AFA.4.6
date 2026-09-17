"""playthrough: events table

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

ID_TYPE = sa.CHAR(26)

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", ID_TYPE, nullable=False),
        sa.Column("campaign_run_id", ID_TYPE, nullable=False),
        sa.Column("actor_member_id", ID_TYPE, nullable=True),
        sa.Column("turn_id", ID_TYPE, nullable=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("visibility", sa.String(length=8), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
        sa.ForeignKeyConstraint(
            ["campaign_run_id"],
            ["campaign_runs.id"],
            name="fk_events_campaign_run_id_campaign_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_member_id"],
            ["campaign_run_members.id"],
            name="fk_events_actor_member_id_campaign_run_members",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "type IN ('narration','player_action','roll','tool_call','error')", name="type"
        ),
        sa.CheckConstraint("visibility IN ('player','dm')", name="visibility"),
    )
    op.create_index(
        "ix_events_campaign_run_id_visibility_id",
        "events",
        ["campaign_run_id", "visibility", "id"],
    )
    op.create_index("ix_events_campaign_run_id_turn_id", "events", ["campaign_run_id", "turn_id"])


def downgrade() -> None:
    op.drop_index("ix_events_campaign_run_id_turn_id", table_name="events")
    op.drop_index("ix_events_campaign_run_id_visibility_id", table_name="events")
    op.drop_table("events")
