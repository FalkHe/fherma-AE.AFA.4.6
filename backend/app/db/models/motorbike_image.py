"""The `motorbike_images` table: one downloaded image per row."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

SOURCE_URL_LENGTH = 2048
ORIGINAL_PATH_LENGTH = 512


class ImageStatus(StrEnum):
    """Moderation state of an image."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class MotorbikeImage(ULIDPrimaryKeyMixin, Base):
    """A picture of one motorbike, awaiting or having passed review.

    `original_path` is relative to `MEDIA_DIR`. The resized variants are
    **never stored**: their paths are derived deterministically from the
    motorbike and image ids.
    """

    __tablename__ = "motorbike_images"

    motorbike_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting a catalogue entry takes its images with it.
        ForeignKey("motorbikes.id", ondelete="CASCADE"),
        index=True,
    )
    source_url: Mapped[str] = mapped_column(String(SOURCE_URL_LENGTH))
    # Licence and author line; NULL when the source carried no usable metadata.
    attribution: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ImageStatus] = mapped_column(
        Enum(
            ImageStatus,
            name="image_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        server_default=ImageStatus.PENDING.value,
    )
    original_path: Mapped[str] = mapped_column(String(ORIGINAL_PATH_LENGTH))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
