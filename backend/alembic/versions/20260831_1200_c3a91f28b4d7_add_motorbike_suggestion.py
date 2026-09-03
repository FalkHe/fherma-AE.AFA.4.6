"""add motorbikes.suggestion

The unverified counterpart of the structured catalogue fields: whatever the
source that proposed a model claimed about it (year range, manufacturer type
codes, links, the raw line it was read from). Hints for ingestion and for the
reviewing admin — never facts, so they stay out of the typed columns.

JSONB and nullable: nothing filters on the document, and every row that exists
today was created without one.

Revision ID: c3a91f28b4d7
Revises: fb2747f937c4
Create Date: 2026-08-31 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a91f28b4d7"
down_revision: str | Sequence[str] | None = "fb2747f937c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.add_column(
        "motorbikes",
        sa.Column("suggestion", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_column("motorbikes", "suggestion")
