"""srd: vector extension, srd_rules table, hnsw cosine index

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import VECTOR

from alembic import op

ID_TYPE = sa.CHAR(26)

# Must match `app.modules.srd.models.EMBEDDING_WIDTH`.
EMBEDDING_WIDTH = 1536

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "srd_rules",
        sa.Column("id", ID_TYPE, nullable=False),
        sa.Column("source_version", sa.String(), nullable=False),
        sa.Column("heading_path", sa.String(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding", VECTOR(EMBEDDING_WIDTH), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_srd_rules"),
    )

    op.create_index(
        "ix_srd_rules_embedding",
        "srd_rules",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_srd_rules_embedding", table_name="srd_rules")
    op.drop_table("srd_rules")
