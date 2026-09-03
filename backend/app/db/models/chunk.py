"""The `chunks` table: retrievable slices of one source document.

A chunk is the unit the advisor retrieves: a piece of a `source_documents` row
small enough to embed and quote, big enough to still carry its context. Rows
are written by the structural chunker (`app.services.chunking`); the embedding
columns stay NULL until the embedding pass fills them, and retrieval only ever
considers rows whose `embedding` is set.

Two deliberate denormalisations live here:

* `motorbike_id` is copied from the owning document, so a retrieval filter on
  the catalogue entry never needs a join.
* `text_tsv` is a stored generated column, so the lexical half of hybrid
  retrieval needs neither a trigger nor an application write.

The table carries **no timestamps**: a chunk has no life of its own — it is
rewritten wholesale whenever its document is re-chunked.
"""

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import ULID_LENGTH, Base, ULIDPrimaryKeyMixin

HEADING_PATH_LENGTH = 512
EMBEDDING_MODEL_LENGTH = 128

# Width of the `vector` column. Pinned in the schema and in the migration: the
# configured `EMBEDDING_DIMENSIONS` must match it, or a migration is required.
EMBEDDING_DIMENSIONS = 1536

# Text-search configuration of the generated `text_tsv` column. The corpus is
# English prose; the same configuration must be used when querying it.
TEXT_SEARCH_CONFIGURATION = "english"


class Chunk(ULIDPrimaryKeyMixin, Base):
    """One retrievable slice of a source document."""

    __tablename__ = "chunks"

    __table_args__ = (
        # Sequence numbers are per document and gap-free, so this is also the
        # guard against a half-finished re-chunk leaving duplicates behind.
        UniqueConstraint("source_document_id", "sequence"),
        # Lexical retrieval reads the generated column through this index.
        Index(None, "text_tsv", postgresql_using="gin"),
        # Approximate nearest-neighbour search on cosine distance. The build
        # parameters are pinned; changing them means rebuilding the index.
        Index(
            None,
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    source_document_id: Mapped[str] = mapped_column(
        String(ULID_LENGTH),
        # Re-ingesting a model replaces its documents; the chunks follow.
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        index=True,
    )
    # Denormalised from the document: retrieval filters on the catalogue entry.
    motorbike_id: Mapped[str] = mapped_column(String(ULID_LENGTH), index=True)
    # Position within the document, starting at 0 — restores reading order.
    sequence: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # "Suzuki GSR600 > Design"; NULL for text above the first heading.
    heading_path: Mapped[str | None] = mapped_column(String(HEADING_PATH_LENGTH))
    # PDF sources only; always NULL while every source is HTML.
    page_number: Mapped[int | None] = mapped_column(SmallInteger)
    # NULL until the embedding pass runs; retrieval skips unembedded rows.
    embedding: Mapped[Any | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    # What produced `embedding`, recorded per row: a model or dimension change
    # must be visible without guessing which rows are stale.
    embedding_model: Mapped[str | None] = mapped_column(String(EMBEDDING_MODEL_LENGTH))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    # Maintained by PostgreSQL, never written by the application. Deferred: it
    # is index input, not something any code path reads.
    text_tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(f"to_tsvector('{TEXT_SEARCH_CONFIGURATION}', text)", persisted=True),
        deferred=True,
    )
