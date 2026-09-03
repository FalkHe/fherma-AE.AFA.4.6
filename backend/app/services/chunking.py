"""Turn a source document's Markdown into retrievable chunks.

Structural chunking only — no semantic or LLM-assisted splitting. The pipeline
is two pinned splitters in sequence:

1. `MarkdownHeaderTextSplitter` cuts the document at its ATX headings. This is
   what makes the chunks *about* something: the heading trail of every section
   is kept and stored as `heading_path` ("Suzuki GSR600 > Design"), so a
   retrieved slice can be attributed without reading it.
2. `RecursiveCharacterTextSplitter` cuts the sections that are still too long,
   preferring paragraph then line then word boundaries, at
   `CHUNK_SIZE_CHARS` with `CHUNK_OVERLAP_CHARS` of overlap. Sections shorter
   than the target size stay whole — one section, one chunk.

Sizes are characters, not tokens: the same no-tokenizer-dependency choice the
extraction budget makes.

**Re-chunking is a replacement**, not an update: a document's existing chunks
are deleted and written again from scratch, which resets `embedding`,
`embedding_model` and `embedding_dimensions` to NULL. That is deliberate — a
chunk's text is its identity, and a rewritten text must never keep the vector
of the text it replaced. The embedding pass fills the columns afterwards.
"""

import logging
from dataclasses import dataclass

from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.chunk import HEADING_PATH_LENGTH, Chunk
from app.db.models.source_document import SourceDocument
from app.services import document_service

logger = logging.getLogger(__name__)

# Heading levels the structural split honours, outermost first. Deeper levels
# stay inside the section they belong to: a `#####` sub-sub-heading is prose,
# not a section of its own.
HEADERS_TO_SPLIT_ON: tuple[tuple[str, str], ...] = (
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
    ("####", "h4"),
)

# How a heading trail is rendered into the single `heading_path` column.
HEADING_SEPARATOR = " > "

# Boundaries the character splitter prefers, best first: paragraph, line, word,
# and finally any character (LangChain's default set, spelled out because the
# chunk sizes here only make sense together with it).
CHARACTER_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", " ", "")

# `MarkdownHeaderTextSplitter` joins the lines of a section with the Markdown
# hard break "  \n", which flattens the blank line between two paragraphs. That
# would leave the character splitter without its best boundary, so the paragraph
# break is restored before the second stage runs.
MARKDOWN_HARD_BREAK = "  \n"
PARAGRAPH_BREAK = "\n\n"


@dataclass(frozen=True, slots=True)
class ChunkCandidate:
    """One slice of a document, before it becomes a row."""

    sequence: int
    text: str
    heading_path: str | None


@dataclass(frozen=True, slots=True)
class RebuildSummary:
    """How much a rebuild rewrote."""

    documents: int
    chunks: int


def split_markdown(
    markdown: str,
    *,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[ChunkCandidate]:
    """Split one document's Markdown into sequenced chunk candidates.

    Sequence numbers are gap-free and start at 0, in reading order, so the
    original document can be reassembled from its chunks. Slices that are only
    whitespace are dropped rather than stored — an empty chunk is retrievable
    noise. Sizes default to the configured ones; the parameters exist so tests
    can work on readable inputs.

    Stored text is whitespace-equivalent to the source, not byte-identical: the
    header splitter's hard breaks are turned back into paragraph breaks (see
    `MARKDOWN_HARD_BREAK`) and each slice is stripped.
    """
    settings = get_settings()
    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=list(HEADERS_TO_SPLIT_ON))
    character_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size if chunk_size is not None else settings.chunk_size_chars,
        chunk_overlap=chunk_overlap if chunk_overlap is not None else settings.chunk_overlap_chars,
        separators=list(CHARACTER_SEPARATORS),
    )

    sections = header_splitter.split_text(markdown)
    for section in sections:
        section.page_content = section.page_content.replace(MARKDOWN_HARD_BREAK, PARAGRAPH_BREAK)

    candidates: list[ChunkCandidate] = []
    for piece in character_splitter.split_documents(sections):
        text = piece.page_content.strip()
        if not text:
            continue
        candidates.append(
            ChunkCandidate(
                sequence=len(candidates),
                text=text,
                heading_path=heading_path(piece.metadata),
            )
        )
    return candidates


def heading_path(metadata: dict[str, str]) -> str | None:
    """Compose the heading trail of one section from the splitter's metadata.

    Returns `None` for text above the first heading (the splitter reports no
    headers for it), and truncates to the column width — a pathological trail
    of long headings must not fail the write.
    """
    headings = [
        heading.strip()
        for _, key in HEADERS_TO_SPLIT_ON
        if (heading := metadata.get(key, "").strip())
    ]
    if not headings:
        return None
    return HEADING_SEPARATOR.join(headings)[:HEADING_PATH_LENGTH]


async def rebuild_document(session: AsyncSession, document: SourceDocument) -> list[Chunk]:
    """Replace every chunk of one document and return the rows written.

    The delete and the insert share one transaction, so a reader never sees a
    document with no chunks at all.
    """
    await session.execute(delete(Chunk).where(Chunk.source_document_id == document.id))
    chunks = [
        Chunk(
            source_document_id=document.id,
            motorbike_id=document.motorbike_id,
            sequence=candidate.sequence,
            text=candidate.text,
            heading_path=candidate.heading_path,
        )
        for candidate in split_markdown(document.content_markdown)
    ]
    for chunk in chunks:
        session.add(chunk)
    await session.commit()

    logger.info(
        "Chunked document %s of motorbike %s into %d chunk(s).",
        document.id,
        document.motorbike_id,
        len(chunks),
    )
    return chunks


async def rebuild_for_motorbike(session: AsyncSession, motorbike_id: str) -> RebuildSummary:
    """Re-chunk every document of one catalogue entry."""
    documents = await document_service.list_for_motorbike(session, motorbike_id)
    written = 0
    for document in documents:
        written += len(await rebuild_document(session, document))
    return RebuildSummary(documents=len(documents), chunks=written)
