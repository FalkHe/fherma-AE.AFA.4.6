"""playthrough: four more event types -- item_moved, hp_changed,
way_opened, rule_looked_up

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-23

Additive and self-reversing: `upgrade()` widens `ck_events_type` from the
twelve values `0007` left in place to sixteen; `downgrade()` restores the
twelve exactly, mirroring `0007_lifecycle_and_event_types.py`'s own
`events.type` step.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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


def upgrade() -> None:
    op.drop_constraint("type", "events", type_="check")
    op.create_check_constraint("type", "events", NEW_EVENT_TYPE_VALUES)


def downgrade() -> None:
    op.drop_constraint("type", "events", type_="check")
    op.create_check_constraint("type", "events", OLD_EVENT_TYPE_VALUES)
