"""add motorbike_used_prices

Third of the phase's four pinned migrations (`docs/roadmap/phase-6/shared-
knowledge.md`, hard rules). Two independent changes, in this order:

1. `ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'listing'` — a used-price
   research source page (D12). This migration only adds the label, it never
   *uses* it in the same transaction, which is what keeps `ADD VALUE` legal
   inside Alembic's transactional DDL on PostgreSQL >= 12 (we run pg16).
2. `motorbike_used_prices` — one full-object-replace used-price snapshot per
   motorbike, per D9's exact column table. No draft/verified kind split (a
   used price is never presented as a signed-off fact); `sample_count` is
   nullable and NULL means "unknown", never "zero" (D8).

**Downgrade note (D12):** PostgreSQL cannot drop a value from an enum type, so
`downgrade()` only drops the table. The `listing` label stays on `source_type`
after a downgrade. This is harmless: nothing in the schema at this revision (or
before it) can reference the value, `source_documents.source_type` simply gains
one more never-written option, and the label is added back idempotently
(`IF NOT EXISTS`) the next time this revision is applied.

Revision ID: d6545d99f81a
Revises: 06db655fd7b4
Create Date: 2026-08-31 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d6545d99f81a"
down_revision: str | Sequence[str] | None = "06db655fd7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'listing'")

    op.create_table(
        "motorbike_used_prices",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("motorbike_id", sa.String(length=26), nullable=False),
        sa.Column("price_min_eur", sa.Integer(), nullable=False),
        sa.Column("price_max_eur", sa.Integer(), nullable=False),
        sa.Column("price_median_eur", sa.Integer(), nullable=False),
        sa.Column("sample_count", sa.SmallInteger(), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
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
        sa.ForeignKeyConstraint(
            ["motorbike_id"],
            ["motorbikes.id"],
            name=op.f("fk_motorbike_used_prices_motorbike_id_motorbikes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_motorbike_used_prices")),
        sa.UniqueConstraint("motorbike_id", name=op.f("uq_motorbike_used_prices_motorbike_id")),
    )


def downgrade() -> None:
    """Revert this revision.

    Only the table is dropped. `source_type`'s `listing` label cannot be
    dropped by PostgreSQL and deliberately remains — see the module docstring.
    """
    op.drop_table("motorbike_used_prices")
