"""The `motorbike_used_prices` table: one researched used-market snapshot per bike.

`msrp_eur`/`price_band` on `motorbike_specs` stay the new-bike, MSRP-derived
fields (D9, `docs/roadmap/stage-01/phase-6/shared-knowledge.md`); this table is the
separate, unrelated used-market figure a research run finds. There is no
draft/verified kind split here — a used price is deliberately never presented
as a signed-off fact, the `as_of` date and `sources` are the honesty mechanism
instead (D9).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin


class MotorbikeUsedPrice(ULIDPrimaryKeyMixin, Base):
    """One full-object-replace used-price snapshot of one motorbike.

    A research run either produces a median and writes the whole row, or it
    produces nothing and writes nothing — the three price columns are
    `NOT NULL` on purpose, there is no partial snapshot.

    `sample_count` is `NULL` when the sources only stated a range rather than a
    counted set of asking prices; **NULL always means "unknown", never
    "zero"** (D8/D9).

    `sources` is a JSONB array, one entry per source document the run drew a
    figure from, snake_case, shaped exactly as:

    ```json
    [
        {
            "source_document_id": "<ULID>",
            "url": "https://example.com/...",
            "title": "Example listing page",
            "sample_count": 3,
            "prices": [4200, 4500, 4800]
        }
    ]
    ```

    `sample_count` inside one `sources` entry follows the same "NULL = unknown"
    rule as the row-level column; `prices` is the list of individual asking
    prices that entry contributed (empty when the source only stated a range).
    """

    __tablename__ = "motorbike_used_prices"
    __table_args__ = (UniqueConstraint("motorbike_id"),)

    motorbike_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting a catalogue entry takes its price snapshot with it.
        ForeignKey("motorbikes.id", ondelete="CASCADE"),
    )
    price_min_eur: Mapped[int] = mapped_column(Integer)
    price_max_eur: Mapped[int] = mapped_column(Integer)
    price_median_eur: Mapped[int] = mapped_column(Integer)
    sample_count: Mapped[int | None] = mapped_column(SmallInteger)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
