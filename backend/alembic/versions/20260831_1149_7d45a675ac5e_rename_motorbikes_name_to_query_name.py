"""rename motorbikes name to query_name

`motorbikes.name` is not a rendered model name — it is the phrase an admin (or
`flag_unknown_bike`) typed. It seeds the ingestion query, is a matching
surface, and is the fallback when a row has no structured identity yet.
Renaming it to `query_name` frees `name` to become the server-rendered name in
a later Phase-6 step. Column type and nullability are unchanged.

Revision ID: 7d45a675ac5e
Revises: c3a91f28b4d7
Create Date: 2026-08-31 11:49:39.068010

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d45a675ac5e"
down_revision: str | Sequence[str] | None = "c3a91f28b4d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.alter_column("motorbikes", "name", new_column_name="query_name")


def downgrade() -> None:
    """Revert this revision."""
    op.alter_column("motorbikes", "query_name", new_column_name="name")
