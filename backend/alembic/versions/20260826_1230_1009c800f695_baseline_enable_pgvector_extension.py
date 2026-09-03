"""baseline: enable pgvector extension

Baseline revision. It creates no tables: it only enables the `vector`
extension, which every later embedding column depends on, and proves that the
migration plumbing reaches the database.

Revision ID: 1009c800f695
Revises:
Create Date: 2026-08-26 12:30:21.386771

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1009c800f695"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Revert this revision."""
    op.execute("DROP EXTENSION IF EXISTS vector")
