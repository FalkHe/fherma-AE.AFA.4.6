"""`app/services/document_service.py` — source-document writes and list ordering.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.
"""

import asyncio
from datetime import UTC, datetime

from app.db.models.source_document import SourceDocument, SourceType
from app.services import document_service, product_service
from tests.services.conftest import FakeAsyncSession

FETCHED_AT = datetime(2026, 8, 26, 10, 30, tzinfo=UTC)


def _create(
    session: FakeAsyncSession,
    motorbike_id: str,
    source_type: SourceType,
    *,
    created_at: datetime,
    source_title: str = "Some page",
    source_url: str | None = "https://example.invalid/page",
) -> SourceDocument:
    """Create a document and stamp `created_at` (a server default in real life)."""
    document = asyncio.run(
        document_service.create_document(
            session,
            motorbike_id,
            source_type=source_type,
            source_title=source_title,
            raw_path=f"sources/{motorbike_id}/doc.html",
            content_markdown="# Heading\n\nBody.",
            fetched_at=FETCHED_AT,
            source_url=source_url,
        )
    )
    document.created_at = created_at
    return document


def test_create_document_stores_the_payload(fake_session: FakeAsyncSession) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    commits_before = fake_session.commit_count

    document = _create(
        fake_session,
        motorbike.id,
        SourceType.WIKIPEDIA,
        created_at=datetime(2026, 8, 26, 11, tzinfo=UTC),
        source_title="Suzuki GSR600",
    )

    assert document.id is not None
    assert document.motorbike_id == motorbike.id
    assert document.source_type is SourceType.WIKIPEDIA
    assert document.source_title == "Suzuki GSR600"
    assert document.raw_path == f"sources/{motorbike.id}/doc.html"
    assert document.content_markdown == "# Heading\n\nBody."
    assert document.fetched_at == FETCHED_AT
    assert fake_session.commit_count == commits_before + 1


def test_create_document_defaults_source_url_to_none(fake_session: FakeAsyncSession) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))

    document = asyncio.run(
        document_service.create_document(
            fake_session,
            motorbike.id,
            source_type=SourceType.UPLOAD,
            source_title="brochure.html",
            raw_path=f"sources/{motorbike.id}/upload.html",
            content_markdown="Body.",
            fetched_at=FETCHED_AT,
        )
    )

    assert document.source_url is None


def test_list_for_motorbike_puts_wikipedia_first_then_created_at(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    magazine = _create(
        fake_session,
        motorbike.id,
        SourceType.MAGAZINE,
        created_at=datetime(2026, 8, 26, 9, tzinfo=UTC),
    )
    technical = _create(
        fake_session,
        motorbike.id,
        SourceType.TECHNICAL,
        created_at=datetime(2026, 8, 26, 10, tzinfo=UTC),
    )
    # Created last, but still expected first.
    wikipedia = _create(
        fake_session,
        motorbike.id,
        SourceType.WIKIPEDIA,
        created_at=datetime(2026, 8, 26, 11, tzinfo=UTC),
    )

    documents = asyncio.run(document_service.list_for_motorbike(fake_session, motorbike.id))

    assert documents == [wikipedia, magazine, technical]


def test_list_for_motorbike_ignores_other_motorbikes(fake_session: FakeAsyncSession) -> None:
    mine = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    other = asyncio.run(product_service.create_backlog(fake_session, "Honda CB 500 F"))
    my_document = _create(
        fake_session,
        mine.id,
        SourceType.PRODUCT,
        created_at=datetime(2026, 8, 26, 9, tzinfo=UTC),
    )
    _create(
        fake_session,
        other.id,
        SourceType.PRODUCT,
        created_at=datetime(2026, 8, 26, 9, tzinfo=UTC),
    )

    assert asyncio.run(document_service.list_for_motorbike(fake_session, mine.id)) == [my_document]


def test_list_for_motorbike_without_documents_is_empty(fake_session: FakeAsyncSession) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))

    assert asyncio.run(document_service.list_for_motorbike(fake_session, motorbike.id)) == []


def test_list_for_motorbike_excludes_the_given_source_types(
    fake_session: FakeAsyncSession,
) -> None:
    """`exclude_source_types` (step 6.21, D12) — the four quarantine call sites."""
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    wikipedia = _create(
        fake_session,
        motorbike.id,
        SourceType.WIKIPEDIA,
        created_at=datetime(2026, 8, 26, 9, tzinfo=UTC),
    )
    _create(
        fake_session,
        motorbike.id,
        SourceType.LISTING,
        created_at=datetime(2026, 8, 26, 10, tzinfo=UTC),
    )

    documents = asyncio.run(
        document_service.list_for_motorbike(
            fake_session, motorbike.id, exclude_source_types=(SourceType.LISTING,)
        )
    )

    assert documents == [wikipedia]


def test_list_for_motorbike_default_is_byte_identical_to_before_6_21(
    fake_session: FakeAsyncSession,
) -> None:
    """Omitting the keyword changes nothing — every pre-6.21 caller is untouched."""
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    wikipedia = _create(
        fake_session,
        motorbike.id,
        SourceType.WIKIPEDIA,
        created_at=datetime(2026, 8, 26, 9, tzinfo=UTC),
    )
    listing = _create(
        fake_session,
        motorbike.id,
        SourceType.LISTING,
        created_at=datetime(2026, 8, 26, 10, tzinfo=UTC),
    )

    documents = asyncio.run(document_service.list_for_motorbike(fake_session, motorbike.id))

    assert documents == [wikipedia, listing]
