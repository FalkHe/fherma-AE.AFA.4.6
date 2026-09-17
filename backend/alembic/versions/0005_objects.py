"""playthrough: objects table

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

ID_TYPE = sa.CHAR(26)

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "objects",
        sa.Column("id", ID_TYPE, nullable=False),
        sa.Column("campaign_run_id", ID_TYPE, nullable=False),
        sa.Column("member_id", ID_TYPE, nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("template_id", sa.String(length=64), nullable=False),
        sa.Column("instance_key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_adventure_id", sa.String(length=64), nullable=True),
        sa.Column("source_scene_id", sa.String(length=64), nullable=True),
        sa.Column("adventure_run_id", ID_TYPE, nullable=True),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("owner_object_id", ID_TYPE, nullable=True),
        sa.Column("current_hp", sa.Integer(), nullable=True),
        sa.Column("max_hp", sa.Integer(), nullable=True),
        sa.Column("armour_class", sa.Integer(), nullable=True),
        sa.Column("is_alive", sa.Boolean(), nullable=True),
        sa.Column(
            "state",
            JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
        sa.PrimaryKeyConstraint("id", name="pk_objects"),
        sa.ForeignKeyConstraint(
            ["campaign_run_id"],
            ["campaign_runs.id"],
            name="fk_objects_campaign_run_id_campaign_runs",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["campaign_run_members.id"],
            name="fk_objects_member_id_campaign_run_members",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["adventure_run_id"],
            ["adventure_runs.id"],
            name="fk_objects_adventure_run_id_adventure_runs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_object_id"],
            ["objects.id"],
            name="fk_objects_owner_object_id_objects",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("campaign_run_id", "instance_key", name="uq_objects_campaign_run_id"),
        sa.CheckConstraint("kind IN ('creature','item','fixture')", name="kind"),
        sa.CheckConstraint(
            "(kind = 'creature') = (current_hp IS NOT NULL) AND "
            "(kind = 'creature') = (max_hp IS NOT NULL) AND "
            "(kind = 'creature') = (armour_class IS NOT NULL) AND "
            "(kind = 'creature') = (is_alive IS NOT NULL)",
            name="stats_creature_only",
        ),
        sa.CheckConstraint(
            "(current_hp IS NULL AND max_hp IS NULL) OR "
            "(current_hp IS NOT NULL AND max_hp IS NOT NULL AND "
            "current_hp >= 0 AND current_hp <= max_hp)",
            name="hp_range",
        ),
        sa.CheckConstraint("(adventure_run_id IS NULL) = (scene_id IS NULL)", name="position"),
        sa.CheckConstraint(
            "owner_object_id IS NULL OR (adventure_run_id IS NULL AND scene_id IS NULL)",
            name="carried",
        ),
    )
    op.create_index("ix_objects_campaign_run_id", "objects", ["campaign_run_id"])
    op.create_index("ix_objects_member_id", "objects", ["member_id"])
    op.create_index("ix_objects_owner_object_id", "objects", ["owner_object_id"])
    op.create_index(
        "ix_objects_adventure_run_id_scene_id", "objects", ["adventure_run_id", "scene_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_objects_adventure_run_id_scene_id", table_name="objects")
    op.drop_index("ix_objects_owner_object_id", table_name="objects")
    op.drop_index("ix_objects_member_id", table_name="objects")
    op.drop_index("ix_objects_campaign_run_id", table_name="objects")
    op.drop_table("objects")
