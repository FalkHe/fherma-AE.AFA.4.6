"""The `motorbike_specs` table: the frozen core specification column set.

Exactly one row per (motorbike, kind). `draft` is what ingestion extracted and
an admin edits; `verified` is what approval promoted and what customer-facing
retrieval filters on. Nothing ever writes a `verified` row except the approval
promotion in `app.services.product_service`.

The column set is **frozen** — Phase-3 tools filter on precisely these fields.
Units are the project-wide ones: mm, kg, kW, Nm, cm³, litres, km/h, EUR.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

CATEGORY_LENGTH = 32
PRICE_BAND_LENGTH = 16

# The frozen column set, in table order: everything a specification revision
# carries apart from its identity (`id`, `motorbike_id`, `kind`). Writes are
# full-object replacements over exactly these fields.
SPEC_FIELDS: tuple[str, ...] = (
    "category",
    "engine_cc",
    "cylinders",
    "power_kw",
    "torque_nm",
    "wet_weight_kg",
    "seat_height_mm",
    "tank_capacity_l",
    "top_speed_kmh",
    "abs",
    "a2_eligible",
    "price_band",
    "msrp_eur",
    "extra",
    "source_hints",
    "extracted_at",
)

# Pinned vocabularies for the two free-text-typed columns. Validation lives at
# the API boundary and in the extraction schema; these tuples are the single
# place the allowed values are spelled out.
SPEC_CATEGORIES: tuple[str, ...] = (
    "naked",
    "sport",
    "sport_touring",
    "touring",
    "adventure",
    "cruiser",
    "classic",
    "scrambler",
    "enduro",
    "supermoto",
    "scooter",
)
# budget < 5 k€ · mid 5–10 k€ · upper 10–15 k€ · premium > 15 k€
PRICE_BANDS: tuple[str, ...] = ("budget", "mid", "upper", "premium")


class SpecKind(StrEnum):
    """Which of the two specification revisions a row holds."""

    DRAFT = "draft"
    VERIFIED = "verified"


class MotorbikeSpec(ULIDPrimaryKeyMixin, Base):
    """One specification revision of one motorbike."""

    __tablename__ = "motorbike_specs"
    __table_args__ = (UniqueConstraint("motorbike_id", "kind"),)

    motorbike_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting a catalogue entry takes its specifications with it.
        ForeignKey("motorbikes.id", ondelete="CASCADE"),
    )
    kind: Mapped[SpecKind] = mapped_column(
        Enum(
            SpecKind,
            name="spec_kind",
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    category: Mapped[str | None] = mapped_column(String(CATEGORY_LENGTH))
    engine_cc: Mapped[int | None] = mapped_column(Integer)
    cylinders: Mapped[int | None] = mapped_column(SmallInteger)
    power_kw: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    torque_nm: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    wet_weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    seat_height_mm: Mapped[int | None] = mapped_column(SmallInteger)
    tank_capacity_l: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    top_speed_kmh: Mapped[int | None] = mapped_column(SmallInteger)
    abs: Mapped[bool | None] = mapped_column(Boolean)
    # Derived on write only when the incoming value is null; an explicit
    # (admin-set) value always wins. See `product_service`.
    a2_eligible: Mapped[bool | None] = mapped_column(Boolean)
    price_band: Mapped[str | None] = mapped_column(String(PRICE_BAND_LENGTH))
    msrp_eur: Mapped[int | None] = mapped_column(Integer)
    # Long tail of specifications; never filtered on.
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # Per-field provenance notes from the extraction step.
    source_hints: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
