"""playthrough: five-value run status defaulting to setup, template-less
creatures, twelve event types

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-18

Additive and self-reversing: `upgrade()` widens `ck_campaign_runs_status`
to the five lifecycle values with `server_default 'setup'`, drops
`objects.template_id`'s `NOT NULL` and widens `ck_events_type` to the
twelve event types; `downgrade()` restores all three exactly.

`downgrade()` restores `objects.template_id NOT NULL`, so it fails against
a database that already holds a row with `template_id IS NULL` -- a
generated character with no template. That is deliberate: no such row can
exist before character creation lands, and silently deleting one instead
of failing loudly would be worse.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUS_VALUES = "status IN ('active','archived','finished')"
NEW_STATUS_VALUES = "status IN ('setup','ready','active','archived','finished')"
OLD_EVENT_TYPE_VALUES = "type IN ('narration','player_action','roll','tool_call','error')"
NEW_EVENT_TYPE_VALUES = (
    "type IN ('narration','player_action','roll_requested','roll','question',"
    "'tool_call','scene_entered','adventure_started','adventure_completed',"
    "'system','error','warning')"
)


def upgrade() -> None:
    op.drop_constraint("status", "campaign_runs", type_="check")
    op.create_check_constraint("status", "campaign_runs", NEW_STATUS_VALUES)
    op.alter_column(
        "campaign_runs",
        "status",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="active",
        server_default="setup",
    )

    op.alter_column(
        "objects",
        "template_id",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        nullable=True,
    )

    op.drop_constraint("type", "events", type_="check")
    op.create_check_constraint("type", "events", NEW_EVENT_TYPE_VALUES)


def downgrade() -> None:
    op.drop_constraint("type", "events", type_="check")
    op.create_check_constraint("type", "events", OLD_EVENT_TYPE_VALUES)

    op.alter_column(
        "objects",
        "template_id",
        existing_type=sa.String(length=64),
        existing_nullable=True,
        nullable=False,
    )

    op.alter_column(
        "campaign_runs",
        "status",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        existing_server_default="setup",
        server_default="active",
    )
    op.drop_constraint("status", "campaign_runs", type_="check")
    op.create_check_constraint("status", "campaign_runs", OLD_STATUS_VALUES)
