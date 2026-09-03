"""add motorbike identity columns

The three columns that carry a generation's structured identity beyond
`manufacturer_id`/`model_name`/years, per
`docs/roadmap/model-naming-data-model.md` §2.1/§2.2:

* `buildingline` — the model family ("GS", "MT", "Africa Twin"), free text
  through one normalisation helper (`product_service.normalise_buildingline`).
  Nullable forever; never part of the identity or the slug.
* `type_codes` — every manufacturer code this generation is known by, a JSONB
  array. Retrieval/lookup metadata only — never identity, never rendered to a
  customer.
* `variants` — every trim of this generation except the base, as spec deltas
  plus free text. The row itself is always the base trim.

No writer lands here (that is `assign_identity`, a later step); this is schema
only, additive and backward compatible with every existing row.

Revision ID: 06db655fd7b4
Revises: 7d45a675ac5e
Create Date: 2026-08-31 12:06:10.024978

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06db655fd7b4"
down_revision: str | Sequence[str] | None = "7d45a675ac5e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUILDINGLINE_LENGTH = 64


def upgrade() -> None:
    """Apply this revision."""
    op.add_column(
        "motorbikes",
        sa.Column("buildingline", sa.String(length=BUILDINGLINE_LENGTH), nullable=True),
    )
    op.add_column(
        "motorbikes",
        sa.Column(
            "type_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "motorbikes",
        sa.Column(
            "variants",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_motorbikes_manufacturer_id_buildingline",
        "motorbikes",
        ["manufacturer_id", "buildingline"],
    )


def downgrade() -> None:
    """Revert this revision."""
    op.drop_index("ix_motorbikes_manufacturer_id_buildingline", table_name="motorbikes")
    op.drop_column("motorbikes", "variants")
    op.drop_column("motorbikes", "type_codes")
    op.drop_column("motorbikes", "buildingline")
