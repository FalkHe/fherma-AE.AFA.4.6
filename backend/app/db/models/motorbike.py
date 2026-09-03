"""The `motorbikes` table: one catalogue entry per model."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

NAME_LENGTH = 160
SLUG_LENGTH = 160
MODEL_NAME_LENGTH = 128
BUILDINGLINE_LENGTH = 64


class MotorbikeStatus(StrEnum):
    """Position of a catalogue entry in the curation workflow.

    Legal transitions are enforced by `app.services.product_service.transition`;
    `rejected` is deliberately **not** terminal (an admin re-queues ingestion).
    """

    BACKLOG = "backlog"
    INGESTING = "ingesting"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class Motorbike(ULIDPrimaryKeyMixin, Base):
    """A motorcycle model the catalogue knows about.

    `query_name` keeps the phrase an admin typed ("Suzuki GSR 600"); `slug` is
    the derived, unique identity used to reject duplicates. Structured fields
    (`manufacturer_id`, `model_name`, years) stay NULL until extraction or an
    admin fills them in.

    The brand lives in the `manufacturers` table, referenced by id: there is no
    relationship, so callers resolve it through `manufacturer_service`.

    `suggestion` is the unverified counterpart of those structured fields: what
    whoever proposed the model claimed about it. It is a hint for ingestion and
    for the reviewing admin — **never** a fact, and never rendered as one.

    `buildingline` is the model family ("GS", "MT", "Africa Twin"): free text,
    drift-guarded by `app.services.product_service.normalise_buildingline`
    rather than by a foreign key (there is no `buildinglines` table — D6).
    Nullable forever and never part of the identity or the slug.

    `type_codes` is every manufacturer code this generation is known by. It is
    retrieval/lookup metadata **only** — never identity, never customer-visible
    — validated and capped by `app.services.identity_validation`.

    `variants` carries every trim of this generation *except the base*: this
    row plus its `motorbike_specs` row already **is** the base trim, and a trim
    never becomes a row of its own (D2). Each entry is a spec delta (a key
    present overrides the base; a key absent means "same as the base") plus a
    free-text description; validated and capped by
    `app.services.identity_validation`.
    """

    __tablename__ = "motorbikes"
    __table_args__ = (
        Index("ix_motorbikes_manufacturer_id_buildingline", "manufacturer_id", "buildingline"),
    )

    query_name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    slug: Mapped[str] = mapped_column(String(SLUG_LENGTH), unique=True)
    # No `ondelete`: nothing ever deletes a manufacturer, so the default NO
    # ACTION is the guard against a dangling reference.
    manufacturer_id: Mapped[str | None] = mapped_column(
        String(ULID_LENGTH), ForeignKey("manufacturers.id"), index=True
    )
    buildingline: Mapped[str | None] = mapped_column(String(BUILDINGLINE_LENGTH))
    model_name: Mapped[str | None] = mapped_column(String(MODEL_NAME_LENGTH))
    year_from: Mapped[int | None] = mapped_column(SmallInteger)
    year_to: Mapped[int | None] = mapped_column(SmallInteger)
    # Free-shape on purpose: a suggestion carries whatever its source knew
    # (year range, type codes, links, the raw line). The keys the importer
    # writes are documented in `app.cli.suggestions`; nothing filters on them,
    # so the column stays a JSON document rather than a set of columns.
    suggestion: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    type_codes: Mapped[list[Any]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    variants: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    status: Mapped[MotorbikeStatus] = mapped_column(
        # Native PostgreSQL enum carrying the member *values* (see `User.role`).
        Enum(
            MotorbikeStatus,
            name="motorbike_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        server_default=MotorbikeStatus.BACKLOG.value,
        # The backlog screen and every filtered list query on this column.
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
