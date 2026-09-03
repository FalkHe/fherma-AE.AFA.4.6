"""`app/services/chunking.py` — the structural chunker and rebuild semantics.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention. Splitter tests pass explicit small sizes so the
inputs stay readable; the configured 3200/400 are exercised once, through the
defaults.
"""

import asyncio
from datetime import UTC, datetime

from app.db.models.chunk import Chunk
from app.db.models.source_document import SourceDocument, SourceType
from app.services import chunking, document_service, product_service
from tests.services.conftest import FakeAsyncSession

FETCHED_AT = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)

ARTICLE = """# Suzuki GSR600

Introductory prose above the first sub-heading.

## Design

The GSR600 is a naked motorcycle.

### Engine

An inline-four borrowed from the GSX-R600.

## Reception

Reviewers praised the engine.
"""


def _document(
    session: FakeAsyncSession, motorbike_id: str, markdown: str, *, created_at: datetime
) -> SourceDocument:
    """Store one source document and stamp `created_at` (a server default)."""
    document = asyncio.run(
        document_service.create_document(
            session,
            motorbike_id,
            source_type=SourceType.WIKIPEDIA,
            source_title="Suzuki GSR600",
            raw_path=f"sources/{motorbike_id}/doc.html",
            content_markdown=markdown,
            fetched_at=FETCHED_AT,
        )
    )
    document.created_at = created_at
    return document


def test_split_markdown_builds_the_heading_path_of_every_section() -> None:
    candidates = chunking.split_markdown(ARTICLE, chunk_size=400, chunk_overlap=40)

    assert [candidate.heading_path for candidate in candidates] == [
        "Suzuki GSR600",
        "Suzuki GSR600 > Design",
        "Suzuki GSR600 > Design > Engine",
        "Suzuki GSR600 > Reception",
    ]
    assert candidates[1].text == "The GSR600 is a naked motorcycle."


def test_split_markdown_numbers_chunks_gap_free_from_zero() -> None:
    candidates = chunking.split_markdown(ARTICLE, chunk_size=400, chunk_overlap=40)

    sequences = [candidate.sequence for candidate in candidates]
    assert sequences == list(range(len(candidates)))
    assert len(set(sequences)) == len(sequences)


def test_split_markdown_leaves_text_above_the_first_heading_unattributed() -> None:
    candidates = chunking.split_markdown("Prose without any heading.")

    assert [(c.heading_path, c.text) for c in candidates] == [(None, "Prose without any heading.")]


def test_split_markdown_splits_an_oversize_section_with_overlap() -> None:
    section = " ".join(f"w{index:03d}" for index in range(200))

    candidates = chunking.split_markdown(f"## Long\n\n{section}", chunk_size=200, chunk_overlap=50)

    assert len(candidates) > 1
    assert all(len(candidate.text) <= 200 for candidate in candidates)
    assert all(candidate.heading_path == "Long" for candidate in candidates)
    # Neighbouring chunks share text: a sentence cut by the boundary stays
    # retrievable from both sides.
    for earlier, later in zip(candidates, candidates[1:], strict=False):
        shared = max(
            (
                length
                for length in range(1, min(len(earlier.text), len(later.text)) + 1)
                if earlier.text[-length:] == later.text[:length]
            ),
            default=0,
        )
        assert shared > 0


def test_split_markdown_keeps_a_short_section_whole() -> None:
    candidates = chunking.split_markdown("## Design\n\nShort section.")

    assert [(c.sequence, c.heading_path, c.text) for c in candidates] == [
        (0, "Design", "Short section.")
    ]


def test_split_markdown_keeps_paragraph_breaks_inside_a_section() -> None:
    """The header splitter flattens blank lines into "  \\n"; they must come back."""
    candidates = chunking.split_markdown("## Design\n\nFirst para.\n\nSecond para.")

    assert [candidate.text for candidate in candidates] == ["First para.\n\nSecond para."]


def test_split_markdown_splits_an_oversize_section_at_paragraph_breaks() -> None:
    paragraphs = [f"Paragraph {index}. " + "filler " * 10 for index in range(6)]

    candidates = chunking.split_markdown(
        "## Long\n\n" + "\n\n".join(paragraphs), chunk_size=200, chunk_overlap=40
    )

    assert len(candidates) > 1
    # Every slice starts at a paragraph, i.e. no paragraph was cut mid-sentence.
    assert all(candidate.text.startswith("Paragraph ") for candidate in candidates)


def test_split_markdown_of_blank_input_yields_nothing() -> None:
    assert chunking.split_markdown("   \n\n\t  ") == []


def test_heading_path_is_truncated_to_the_column_width() -> None:
    metadata = {"h1": "a" * 400, "h2": "b" * 400}

    assert len(chunking.heading_path(metadata)) == 512


def test_rebuild_document_writes_provenance_on_every_chunk(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    document = _document(
        fake_session, motorbike.id, ARTICLE, created_at=datetime(2026, 8, 26, 11, tzinfo=UTC)
    )

    written = asyncio.run(chunking.rebuild_document(fake_session, document))

    assert written
    assert all(chunk.source_document_id == document.id for chunk in written)
    assert all(chunk.motorbike_id == motorbike.id for chunk in written)
    assert all(chunk.page_number is None for chunk in written)
    assert all(chunk.embedding is None for chunk in written)
    assert all(chunk.embedding_model is None for chunk in written)
    assert all(chunk.embedding_dimensions is None for chunk in written)
    assert fake_session.rows(Chunk) == written


def test_rebuild_document_replaces_the_previous_chunks(fake_session: FakeAsyncSession) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    document = _document(
        fake_session, motorbike.id, ARTICLE, created_at=datetime(2026, 8, 26, 11, tzinfo=UTC)
    )
    first = asyncio.run(chunking.rebuild_document(fake_session, document))
    # A stale embedding on a chunk that is about to be rewritten.
    first[0].embedding_model = "openai/text-embedding-3-small"

    document.content_markdown = "## Design\n\nA rewritten document."
    second = asyncio.run(chunking.rebuild_document(fake_session, document))

    assert fake_session.rows(Chunk) == second
    assert [chunk.text for chunk in second] == ["A rewritten document."]
    assert [chunk.sequence for chunk in second] == [0]
    assert all(chunk.embedding_model is None for chunk in second)


def test_rebuild_document_keeps_another_documents_chunks(fake_session: FakeAsyncSession) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    mine = _document(
        fake_session, motorbike.id, ARTICLE, created_at=datetime(2026, 8, 26, 11, tzinfo=UTC)
    )
    other = _document(
        fake_session,
        motorbike.id,
        "## Reception\n\nAnother document.",
        created_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )
    kept = asyncio.run(chunking.rebuild_document(fake_session, other))

    asyncio.run(chunking.rebuild_document(fake_session, mine))

    surviving = [
        chunk for chunk in fake_session.rows(Chunk) if chunk.source_document_id == other.id
    ]
    assert surviving == kept


def test_rebuild_for_motorbike_covers_every_document(fake_session: FakeAsyncSession) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))
    _document(fake_session, motorbike.id, ARTICLE, created_at=datetime(2026, 8, 26, 11, tzinfo=UTC))
    _document(
        fake_session,
        motorbike.id,
        "## Reception\n\nAnother document.",
        created_at=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )

    summary = asyncio.run(chunking.rebuild_for_motorbike(fake_session, motorbike.id))

    assert summary.documents == 2
    assert summary.chunks == len(fake_session.rows(Chunk))
    # Sequences are per document, so both documents start at 0.
    assert sorted(chunk.sequence for chunk in fake_session.rows(Chunk)).count(0) == 2


def test_rebuild_for_motorbike_without_documents_writes_nothing(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR600"))

    summary = asyncio.run(chunking.rebuild_for_motorbike(fake_session, motorbike.id))

    assert summary == chunking.RebuildSummary(documents=0, chunks=0)
    assert fake_session.rows(Chunk) == []
