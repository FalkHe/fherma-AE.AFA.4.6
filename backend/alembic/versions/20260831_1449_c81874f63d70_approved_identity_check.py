"""approved identity check

Fourth and final of the phase's four pinned migrations (`docs/roadmap/phase-6/
shared-knowledge.md`, hard rules; D4). Adds
`ck_motorbikes_approved_identity_complete`: an `approved` row must carry
`manufacturer_id`, `model_name` and `year_from` — D4's completeness guard,
enforced in the database, not just in `product_service.transition`.

Added `NOT VALID` then `VALIDATE`d in the same migration (D4's two-step),
**after** 6.18's `app catalogue backfill-identity` and the sourced
`set-identity` calls that filled the 15 previously-incomplete approved rows —
this is the stated ordering exception: the constraint depends on data the
backfill produces, so it cannot sit in M1 with the other model changes.
`NOT VALID` means the constraint is enforced for every write from this point
on without an exclusive table lock scanning existing rows first; `VALIDATE`
then scans the existing data and fails the upgrade loudly if any approved row
still violates it (D4).

Revision ID: c81874f63d70
Revises: d6545d99f81a
Create Date: 2026-08-31 14:49:43.303094

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c81874f63d70"
down_revision: str | Sequence[str] | None = "d6545d99f81a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT_NAME = "ck_motorbikes_approved_identity_complete"
_CONSTRAINT_SQL = (
    "status <> 'approved' OR "
    "(manufacturer_id IS NOT NULL AND model_name IS NOT NULL AND year_from IS NOT NULL)"
)


def upgrade() -> None:
    """Apply this revision."""
    op.execute(
        f"ALTER TABLE motorbikes ADD CONSTRAINT {_CONSTRAINT_NAME} "
        f"CHECK ({_CONSTRAINT_SQL}) NOT VALID"
    )
    op.execute(f"ALTER TABLE motorbikes VALIDATE CONSTRAINT {_CONSTRAINT_NAME}")


def downgrade() -> None:
    """Revert this revision: drop the constraint, nothing else.

    Plain `op.execute`, not `op.drop_constraint`: the constraint's name
    already carries the `ck_` prefix (matching the naming convention's own
    output), and `op.drop_constraint` would apply that convention a second
    time, looking for `ck_motorbikes_ck_motorbikes_...`.
    """
    op.execute(f"ALTER TABLE motorbikes DROP CONSTRAINT {_CONSTRAINT_NAME}")
