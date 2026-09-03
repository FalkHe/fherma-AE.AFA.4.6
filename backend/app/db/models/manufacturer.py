"""The `manufacturers` table: one row per motorcycle brand.

A manufacturer is a first-class catalogue entity instead of the free-text column
`motorbikes.manufacturer` used to be: `slug` is the identity every writer
deduplicates on ("BMW " and "bmw" are the same brand), while `name` keeps the
display casing of whoever saw the brand first.

`description` and `logo_path` exist for the admin surface that does not exist
yet, so both stay NULL for now. `logo_path` is MEDIA_DIR-relative, exactly like
`motorbike_images.original_path` — never an external URL.

As everywhere in this schema: no ORM relationships. A caller that needs the
brand of a catalogue row looks it up through `manufacturer_service`.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base, ULIDPrimaryKeyMixin

NAME_LENGTH = 64
SLUG_LENGTH = 64
LOGO_PATH_LENGTH = 512


class Manufacturer(ULIDPrimaryKeyMixin, Base):
    """A motorcycle brand referenced by catalogue entries."""

    __tablename__ = "manufacturers"

    # Display form, first-seen casing: "Suzuki".
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    # The get-or-create identity; same slugify rule as `motorbikes.slug`.
    slug: Mapped[str] = mapped_column(String(SLUG_LENGTH), unique=True)
    # Both stay NULL until an admin surface can fill them (see module docstring).
    description: Mapped[str | None] = mapped_column(Text)
    logo_path: Mapped[str | None] = mapped_column(String(LOGO_PATH_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
