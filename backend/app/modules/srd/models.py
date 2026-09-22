from datetime import datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.ids import ID_TYPE, generate_id

# Dimensionality of every stored embedding. Pinned here so the model, the
# migration and any caller that validates an embedding before insert share
# one source of truth (see `SrdVectorWidthError`).
EMBEDDING_WIDTH = 1536


class SrdRule(Base):
    """One citable SRD passage and its embedding.

    Owned by nobody: `service.ingest` replaces the whole table on re-ingest
    rather than diffing rows (`module-structure.md` §2).
    """

    __tablename__ = "srd_rules"

    id: Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)
    source_version: Mapped[str] = mapped_column(String, nullable=False)
    heading_path: Mapped[str] = mapped_column(String, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_WIDTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("source_version", "heading_path", "ordinal"),)


Index(
    "ix_srd_rules_embedding",
    SrdRule.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
)
