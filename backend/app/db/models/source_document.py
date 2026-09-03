"""The `source_documents` table: one ingested source text per row."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

SOURCE_URL_LENGTH = 2048
SOURCE_TITLE_LENGTH = 512
RAW_PATH_LENGTH = 512


class SourceType(StrEnum):
    """Where a document came from; also drives list ordering and prompts."""

    WIKIPEDIA = "wikipedia"
    PRODUCT = "product"
    TECHNICAL = "technical"
    MAGAZINE = "magazine"
    UPLOAD = "upload"
    # A used-price research source page (6.13/D12). Quarantined from RAG
    # ingestion/embedding, from spec extraction, from re-ingestion deletes and
    # from the customer-facing `sources[]` projection — enforced in 6.21, not
    # here.
    LISTING = "listing"


class SourceDocument(ULIDPrimaryKeyMixin, Base):
    """Prose about one motorbike, as fetched from a single source.

    `content_markdown` is the extracted main text used for chunking and spec
    extraction; `raw_path` points at the untouched original (relative to
    `DATA_DIR`) so a re-extraction never needs to re-fetch the network.
    """

    __tablename__ = "source_documents"

    motorbike_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Deleting a catalogue entry takes its documents with it.
        ForeignKey("motorbikes.id", ondelete="CASCADE"),
        index=True,
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(
            SourceType,
            name="source_type",
            values_callable=lambda enum: [member.value for member in enum],
        )
    )
    # Uploads have no URL.
    source_url: Mapped[str | None] = mapped_column(String(SOURCE_URL_LENGTH))
    source_title: Mapped[str] = mapped_column(String(SOURCE_TITLE_LENGTH))
    raw_path: Mapped[str] = mapped_column(String(RAW_PATH_LENGTH))
    content_markdown: Mapped[str] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
