"""playthrough: narration embeddings on events, partial hnsw cosine index

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-21

Additive and self-reversing: `upgrade()` adds two nullable columns --
`events.embedding` and `events.embedding_model` -- then a partial HNSW
`vector_cosine_ops` index restricted to `type = 'narration' AND embedding
IS NOT NULL`, so only narration rows that actually carry a vector are ever
indexed. No `CREATE EXTENSION` here: `0002_srd_rules.py` already installs
`vector` and it is shared across the database. `downgrade()` drops the
index before the columns, undoing exactly this and nothing `0007` touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

# Must match `app.modules.playthrough.models.EMBEDDING_WIDTH`.
EMBEDDING_WIDTH = 1536

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("events", sa.Column("embedding", VECTOR(EMBEDDING_WIDTH), nullable=True))
    op.add_column("events", sa.Column("embedding_model", sa.String(), nullable=True))

    op.create_index(
        "ix_events_embedding_narration",
        "events",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        postgresql_where=sa.text("type = 'narration' AND embedding IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_events_embedding_narration", table_name="events")
    op.drop_column("events", "embedding_model")
    op.drop_column("events", "embedding")
