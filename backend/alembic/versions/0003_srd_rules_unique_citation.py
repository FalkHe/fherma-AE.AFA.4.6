"""srd: unique citation -- (source_version, heading_path, ordinal)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_srd_rules_source_version",
        "srd_rules",
        ["source_version", "heading_path", "ordinal"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_srd_rules_source_version", "srd_rules", type_="unique")
