"""Tests for the ingestion orchestration service (steps 2.14 and 2.17).

Every adapter is replaced: `wikipedia.lookup`, the search provider,
`fetch.fetch_html`, `extract.extract_markdown`, `image_service.ingest_image`
and the LLM call behind the extraction stage (`llm.extraction.extract_spec`)
are stubbed, so what is under test is the composition — the pinned milestone
sequence and its exact messages, the partial-failure rule, the zero-document
failure, the retry decision and fresh-run replacement. No socket is opened (a
sentinel stands in for the HTTP client) and the catalogue writes go through the
in-memory `FakeAsyncSession`, so `product_service`, `document_service`,
`operation_service` and `spec_extraction_service` really run.

Retained payloads *are* written: `DATA_DIR` and `MEDIA_DIR` are pointed at
`tmp_path`, because "the previous run's files are deleted" is part of the
contract under test.
"""

import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.core.config import get_settings
from app.db.models.chunk import Chunk
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.db.models.motorbike_spec import MotorbikeSpec, SpecKind
from app.db.models.operation import Operation, OperationStatus
from app.db.models.source_document import SourceDocument, SourceType
from app.jobs import TransientJobError
from app.llm import embeddings as llm_embeddings
from app.llm import extraction
from app.llm.models import MissingApiKeyError
from app.services import (
    document_service,
    embedding_service,
    image_service,
    operation_service,
    product_service,
    spec_extraction_service,
)
from app.services.ingestion import extract, fetch, search, service, storage, wikipedia
from tests.services.conftest import FakeAsyncSession
from tests.services.ingestion.conftest import FakeEmbeddings

# The service only passes the client on to the (stubbed) adapters.
CLIENT: Any = object()

MODEL_NAME = "Suzuki GSR 600"

WIKIPEDIA_PAGE = wikipedia.WikipediaPage(
    key="Suzuki_GSR600",
    title="Suzuki GSR600",
    url="https://en.wikipedia.org/wiki/Suzuki_GSR600",
)
WIKIPEDIA_IMAGE = wikipedia.WikipediaImage(
    url="https://upload.wikimedia.org/gsr600.jpg",
    attribution="Someone · CC BY-SA 4.0",
)


# --- fixtures -----------------------------------------------------------------


@pytest.fixture(autouse=True)
def data_directories(
    settings_override: Callable[..., None], tmp_path: Path
) -> Iterator[dict[str, Path]]:
    """Point both retention directories at the test's own tree."""
    directories = {"data": tmp_path / "data", "media": tmp_path / "media"}
    settings_override(DATA_DIR=directories["data"], MEDIA_DIR=directories["media"])
    yield directories


@pytest.fixture
def motorbike(fake_session: FakeAsyncSession) -> Motorbike:
    """A catalogue entry in `ingesting`, as the job finds it."""
    bike = asyncio.run(product_service.create_backlog(fake_session, MODEL_NAME))
    asyncio.run(product_service.transition(fake_session, bike, MotorbikeStatus.INGESTING))
    return bike


@pytest.fixture
def operation(fake_session: FakeAsyncSession, motorbike: Motorbike) -> Operation:
    """The `queued` operation row the enqueuing side created."""
    return asyncio.run(
        operation_service.create(
            fake_session,
            product_service.INGESTION_OPERATION_TYPE,
            entity_type=operation_service.MOTORBIKE_ENTITY_TYPE,
            entity_id=motorbike.id,
        )
    )


@pytest.fixture
def milestones(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    """Record every `(progress, message)` the run reports, in order."""
    recorded: list[tuple[int, str]] = []
    real_advance = operation_service.advance

    async def spy(session: Any, operation: Operation, progress: int, message: str | None = None):
        recorded.append((progress, message or ""))
        return await real_advance(session, operation, progress, message)

    monkeypatch.setattr(operation_service, "advance", spy)
    return recorded


# --- adapter stubs ------------------------------------------------------------


def _stub_wikipedia(monkeypatch: pytest.MonkeyPatch, outcome: wikipedia.WikipediaOutcome) -> None:
    async def lookup(name: str, *, client: Any = None, gate: Any = None):
        assert name == MODEL_NAME
        assert client is CLIENT
        return outcome

    monkeypatch.setattr(wikipedia, "lookup", lookup)


def _stub_search(
    monkeypatch: pytest.MonkeyPatch, results: search.SearchResults
) -> list[tuple[search.QueryTemplate, ...]]:
    """Stub the provider; returns the `templates` tuple(s) it was called with."""
    captured: list[tuple[search.QueryTemplate, ...]] = []

    class _Provider:
        async def search(
            self,
            name: str,
            *,
            client: Any = None,
            gate: Any = None,
            templates: tuple[search.QueryTemplate, ...] = search.QUERY_TEMPLATES,
        ):
            assert client is CLIENT
            captured.append(templates)
            return results

    monkeypatch.setattr(search, "get_search_provider", _Provider)
    return captured


def _stub_fetch(
    monkeypatch: pytest.MonkeyPatch, outcomes: dict[str, fetch.FetchOutcome]
) -> list[str]:
    fetched: list[str] = []

    async def fetch_html(url: str, *, client: Any = None, gate: Any = None):
        fetched.append(url)
        return outcomes[url]

    monkeypatch.setattr(fetch, "fetch_html", fetch_html)
    return fetched


def _stub_extract(monkeypatch: pytest.MonkeyPatch, outcome: extract.ExtractOutcome) -> None:
    monkeypatch.setattr(extract, "extract_markdown", lambda html, *, url=None: outcome)


def _stub_image(monkeypatch: pytest.MonkeyPatch, outcome: image_service.ImageOutcome) -> None:
    async def ingest_image(session, motorbike_id, image_url, attribution=None, **kwargs: Any):
        assert image_url == WIKIPEDIA_IMAGE.url
        assert attribution == WIKIPEDIA_IMAGE.attribution
        return outcome

    monkeypatch.setattr(image_service, "ingest_image", ingest_image)


def _wikipedia_result(image: wikipedia.WikipediaImage | None = None) -> wikipedia.WikipediaResult:
    return wikipedia.WikipediaResult(
        page=WIKIPEDIA_PAGE,
        content=b"<html>wikipedia</html>",
        markdown="# Suzuki GSR600\n\nA naked bike.",
        image=image,
    )


def _fetch_result(url: str) -> fetch.FetchResult:
    return fetch.FetchResult(
        url=url,
        status_code=200,
        content_type="text/html",
        content=b"<html>page</html>",
        encoding="utf-8",
    )


def _candidate(url: str, source_type: SourceType) -> search.SearchCandidate:
    return search.SearchCandidate(url=url, title=f"Title of {url}", source_type=source_type)


def _document_events(fake_session: FakeAsyncSession) -> list[dict[str, Any]]:
    payloads = [json.loads(payload) for _channel, payload in fake_session.notifications]
    return [payload for payload in payloads if payload["event"] == "document.updated"]


# --- the successful run -------------------------------------------------------


def test_successful_run_walks_the_pinned_milestones(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    milestones: list[tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result(WIKIPEDIA_IMAGE))
    _stub_search(
        monkeypatch,
        search.SearchResults(
            candidates=(
                _candidate("https://suzuki.example/gsr600", SourceType.PRODUCT),
                _candidate("https://bikes.example/gsr600-test", SourceType.MAGAZINE),
            )
        ),
    )
    _stub_fetch(
        monkeypatch,
        {
            "https://suzuki.example/gsr600": _fetch_result("https://suzuki.example/gsr600"),
            "https://bikes.example/gsr600-test": _fetch_result("https://bikes.example/gsr600-test"),
        },
    )
    _stub_extract(monkeypatch, extract.ExtractResult(markdown="## Data\n\n599 cc."))
    _stub_image(
        monkeypatch,
        image_service.ImageResult(
            image=MotorbikeImage(
                id="0" * 26,
                motorbike_id=motorbike.id,
                source_url=WIKIPEDIA_IMAGE.url,
                status=ImageStatus.PENDING,
                original_path="motorbikes/x/y_original.jpg",
            ),
            original_path="motorbikes/x/y_original.jpg",
            variant_paths={},
        ),
    )

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert milestones == [
        (5, "Looking up Wikipedia"),
        (15, "Searching the web"),
        (20, "Fetching sources (1/2)"),
        (40, "Fetching sources (2/2)"),
        (65, "Processing images"),
        (80, "Extracting specifications"),
        (90, "Generating embeddings"),
    ]
    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.progress == 100
    assert motorbike.status is MotorbikeStatus.IN_REVIEW


def test_successful_run_stores_every_document_with_its_provenance(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
    data_directories: dict[str, Path],
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(
        monkeypatch,
        search.SearchResults(
            candidates=(_candidate("https://suzuki.example/gsr600", SourceType.PRODUCT),)
        ),
    )
    _stub_fetch(
        monkeypatch,
        {"https://suzuki.example/gsr600": _fetch_result("https://suzuki.example/gsr600")},
    )
    _stub_extract(monkeypatch, extract.ExtractResult(markdown="## Data\n\n599 cc."))

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    documents = fake_session.rows(SourceDocument)
    assert [document.source_type for document in documents] == [
        SourceType.WIKIPEDIA,
        SourceType.PRODUCT,
    ]
    article = documents[0]
    # The matched title is the admin's disambiguation guard, the human URL the
    # link they click — never the REST endpoint we fetched.
    assert (article.source_title, article.source_url) == (
        WIKIPEDIA_PAGE.title,
        WIKIPEDIA_PAGE.url,
    )
    assert article.content_markdown.startswith("# Suzuki GSR600")
    # The raw payload is retained under the row's own id.
    assert article.raw_path == f"sources/{motorbike.id}/{article.id}.html"
    for document in documents:
        assert storage.resolve(document.raw_path).is_file()
        assert (data_directories["data"] / document.raw_path).is_file()


def test_successful_run_emits_document_updated_per_document(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    documents = fake_session.rows(SourceDocument)
    assert _document_events(fake_session) == [
        {
            "event": "document.updated",
            "productId": motorbike.id,
            "documentId": documents[0].id,
        }
    ]


# --- partial failures ---------------------------------------------------------


def test_partial_failures_become_warnings_and_the_run_still_succeeds(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    milestones: list[tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(
        monkeypatch,
        search.SearchResults(
            candidates=(
                _candidate("https://dead.example/gsr600", SourceType.PRODUCT),
                _candidate("https://empty.example/gsr600", SourceType.MAGAZINE),
            ),
            warnings=("Web search for one query failed.",),
        ),
    )
    _stub_fetch(
        monkeypatch,
        {
            "https://dead.example/gsr600": fetch.FetchFailure(
                url="https://dead.example/gsr600",
                reason=fetch.FetchFailureReason.HTTP_ERROR,
                detail="https://dead.example/gsr600 answered HTTP 404.",
            ),
            "https://empty.example/gsr600": _fetch_result("https://empty.example/gsr600"),
        },
    )
    _stub_extract(
        monkeypatch,
        extract.ExtractFailure(
            reason=extract.ExtractFailureReason.EMPTY,
            detail="No main text extracted from https://empty.example/gsr600.",
        ),
    )

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    # The warning collected so far travels along in the milestone message.
    assert milestones[3] == (
        40,
        "Fetching sources (2/2) — Web search for one query failed.; "
        "https://dead.example/gsr600 answered HTTP 404.",
    )
    # One usable document is enough: the run succeeds and the model is reviewable.
    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    assert len(fake_session.rows(SourceDocument)) == 1
    # ...and the end state says what was missed.
    assert operation.message is not None
    assert operation.message.startswith(service.WARNING_SUMMARY_PREFIX)
    assert "answered HTTP 404" in operation.message
    assert "No main text extracted" in operation.message
    assert operation.error is None


def test_a_failing_image_is_a_warning_not_a_failure(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result(WIKIPEDIA_IMAGE))
    _stub_search(monkeypatch, search.SearchResults())
    _stub_image(
        monkeypatch,
        image_service.ImageFailure(
            url=WIKIPEDIA_IMAGE.url,
            reason=image_service.ImageFailureReason.DOWNLOAD_FAILED,
            detail="Timed out downloading the image.",
        ),
    )

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    assert operation.message is not None
    assert "Timed out downloading the image." in operation.message


def test_a_missing_search_key_leaves_a_wikipedia_only_run(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    milestones: list[tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning = "Web search skipped: TAVILY_API_KEY is not configured."
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults(warnings=(warning,)))

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    # No candidates means no fetch milestones at all — 15 % goes straight to 65 %.
    assert milestones == [
        (5, "Looking up Wikipedia"),
        (15, "Searching the web"),
        (65, f"Processing images — {warning}"),
        (80, f"Extracting specifications — {warning}"),
        (90, f"Generating embeddings — {warning}"),
        (100, service.WARNING_SUMMARY_PREFIX + warning),
    ]
    assert operation.status is OperationStatus.SUCCEEDED
    assert len(fake_session.rows(SourceDocument)) == 1


# --- the extraction stage (step 2.17) -----------------------------------------


def test_the_extraction_stage_writes_the_draft_specification(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    extracted_specs: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The stage reads what the run just stored and fills the review form."""
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert extracted_specs == [MODEL_NAME]
    specs = fake_session.rows(MotorbikeSpec)
    assert [spec.kind for spec in specs] == [SpecKind.DRAFT]
    assert specs[0].engine_cc == 599
    assert specs[0].extracted_at is not None
    assert operation.status is OperationStatus.SUCCEEDED


def test_a_missing_llm_key_is_a_warning_and_the_model_still_reaches_review(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    milestones: list[tuple[int, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic configuration failure: warned about, never retried, never fatal.

    The admin fills the specification form in by hand — that is the correction
    mechanism for extraction anyway — so the documents this run fetched must not
    be thrown away over a missing key.
    """
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    async def raise_missing_key(name: str, documents: Any, *, model: str | None = None):
        raise MissingApiKeyError

    monkeypatch.setattr(extraction, "extract_spec", raise_missing_key)

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    assert operation.message is not None
    assert operation.message.startswith(service.WARNING_SUMMARY_PREFIX)
    assert spec_extraction_service.MISSING_KEY_DETAIL in operation.message
    assert operation.error is None
    # The run kept its document and simply has no draft specification yet.
    assert len(fake_session.rows(SourceDocument)) == 1
    assert fake_session.rows(MotorbikeSpec) == []
    assert milestones[-1][0] == 100


def test_a_failing_extraction_is_a_warning_not_a_failure(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    async def fail(name: str, documents: Any, *, model: str | None = None):
        raise RuntimeError("OpenRouter answered 502")

    monkeypatch.setattr(extraction, "extract_spec", fail)

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    assert operation.message is not None
    assert "OpenRouter answered 502" in operation.message


# --- the embedding stage (step 2.19) ------------------------------------------


def test_the_embedding_stage_chunks_and_embeds_every_document(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    fake_embeddings: FakeEmbeddings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 90 % stage turns the documents this run stored into embedded chunks."""
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    chunks = fake_session.rows(Chunk)
    assert chunks
    assert fake_embeddings.texts == [chunk.text for chunk in chunks]
    assert all(chunk.motorbike_id == motorbike.id for chunk in chunks)
    assert all(chunk.embedding is not None for chunk in chunks)
    assert all(chunk.embedding_model == get_settings().embedding_model for chunk in chunks)
    assert all(
        chunk.embedding_dimensions == get_settings().embedding_dimensions for chunk in chunks
    )
    assert operation.status is OperationStatus.SUCCEEDED


def test_a_missing_embeddings_key_is_a_warning_and_the_model_still_reaches_review(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deterministic configuration failure: chunks are still written, no vectors.

    `app embeddings rebuild` backfills them, so nothing this run fetched may be
    thrown away over a missing key.
    """
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    def raise_missing_key(model: str | None = None) -> Any:
        raise MissingApiKeyError

    monkeypatch.setattr(llm_embeddings, "get_embeddings", raise_missing_key)

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    assert operation.error is None
    assert operation.message is not None
    assert embedding_service.MISSING_KEY_DETAIL in operation.message
    # Chunked, not embedded: the retrievable text exists and waits for vectors.
    assert fake_session.rows(Chunk)
    assert all(chunk.embedding is None for chunk in fake_session.rows(Chunk))


def test_a_failing_embeddings_gateway_is_a_warning_not_a_failure(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())
    monkeypatch.setattr(embedding_service, "TRANSIENT_RETRY_DELAY_SECONDS", 0)

    class _Broken:
        async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("OpenRouter answered 502")

    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: _Broken())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    assert operation.message is not None
    assert "OpenRouter answered 502" in operation.message
    assert all(chunk.embedding is None for chunk in fake_session.rows(Chunk))


def test_a_dimension_mismatch_fails_the_run_loudly(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    settings_override: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one embedding failure that is not a warning: a deployment mistake."""
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())
    settings_override(EMBEDDING_DIMENSIONS=768)

    with pytest.raises(embedding_service.DimensionMismatchError) as raised:
        asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert "alembic" in str(raised.value)
    # Not swallowed into the operation message: the job marks it failed.
    assert operation.message is not None
    assert operation.message == "Generating embeddings"


# --- the failure paths --------------------------------------------------------


def test_zero_documents_fails_deterministically_and_returns_the_bike_to_backlog(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(
        monkeypatch,
        wikipedia.WikipediaFailure(
            reason=wikipedia.WikipediaFailureReason.NO_MATCH,
            detail=f"No Wikipedia article matched {MODEL_NAME!r}.",
        ),
    )
    _stub_search(monkeypatch, search.SearchResults(warnings=("Web search skipped.",)))

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.FAILED
    assert operation.error is not None
    assert operation.error.startswith(service.NO_DOCUMENTS_ERROR)
    assert "No Wikipedia article matched" in operation.error
    # The bike is retryable again, and the image stage never ran.
    assert motorbike.status is MotorbikeStatus.BACKLOG
    assert fake_session.rows(SourceDocument) == []
    assert fake_session.rows(MotorbikeImage) == []


def test_zero_documents_caused_by_the_network_raises_a_transient_error(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(
        monkeypatch,
        wikipedia.WikipediaFailure(
            reason=wikipedia.WikipediaFailureReason.ARTICLE_FETCH_FAILED,
            detail="Could not fetch the Wikipedia article: timeout.",
        ),
    )
    _stub_search(monkeypatch, search.SearchResults())

    with pytest.raises(TransientJobError) as raised:
        asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert service.NO_DOCUMENTS_ERROR in str(raised.value)
    # The same run is about to be attempted again: nothing is closed off.
    assert operation.status is OperationStatus.RUNNING
    assert motorbike.status is MotorbikeStatus.INGESTING


def test_a_failed_candidate_fetch_alone_never_raises_a_transient_error(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timeout on a search candidate is retryable *only* if nothing was stored."""
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(
        monkeypatch,
        search.SearchResults(candidates=(_candidate("https://slow.example", SourceType.PRODUCT),)),
    )
    _stub_fetch(
        monkeypatch,
        {
            "https://slow.example": fetch.FetchFailure(
                url="https://slow.example",
                reason=fetch.FetchFailureReason.TIMEOUT,
                detail="Timed out fetching https://slow.example.",
            )
        },
    )

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW


def test_abandon_leaves_a_bike_alone_that_is_no_longer_ingesting(
    fake_session: FakeAsyncSession, motorbike: Motorbike, operation: Operation
) -> None:
    asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.IN_REVIEW))

    asyncio.run(service.abandon(fake_session, motorbike, operation, "boom"))

    assert operation.status is OperationStatus.FAILED
    assert operation.error == "boom"
    assert motorbike.status is MotorbikeStatus.IN_REVIEW


# --- fresh-run semantics ------------------------------------------------------


def test_re_ingestion_replaces_the_documents_and_the_image_of_the_previous_run(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_id = "1" * 26
    stale_raw = storage.save_raw_document(motorbike.id, stale_id, b"<html>old</html>")
    asyncio.run(
        document_service.create_document(
            fake_session,
            motorbike.id,
            document_id=stale_id,
            source_type=SourceType.WIKIPEDIA,
            source_title="Stale article",
            raw_path=stale_raw,
            content_markdown="old",
            fetched_at=operation.created_at,
        )
    )
    stale_image_id = "2" * 26
    stale_original = image_service.original_path(motorbike.id, stale_image_id, ".jpg")
    stale_variant = image_service.variant_path(motorbike.id, stale_image_id, "thumb")
    for relative in (stale_original, stale_variant):
        path = image_service.resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"old")
    fake_session.add(
        MotorbikeImage(
            id=stale_image_id,
            motorbike_id=motorbike.id,
            source_url="https://old.example/photo.jpg",
            status=ImageStatus.PENDING,
            original_path=stale_original,
        )
    )

    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    documents = fake_session.rows(SourceDocument)
    assert [document.id for document in documents] != [stale_id]
    assert len(documents) == 1
    assert fake_session.rows(MotorbikeImage) == []
    # Rows and files go together: nothing of the previous run is left behind.
    assert not storage.resolve(stale_raw).exists()
    assert not image_service.resolve(stale_original).exists()
    assert not image_service.resolve(stale_variant).exists()
    assert storage.resolve(documents[0].raw_path).is_file()


# --- `listing` documents are quarantined from re-ingestion (step 6.21, D12) ----


def test_re_ingestion_never_discards_a_listing_document_row_or_file(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `listing` document is researched price provenance, not stale ingestion
    output (D12, first carve-out): a re-ingestion must neither delete its row
    nor unlink its file, on top of discarding a stale `wikipedia` document
    exactly as before this step.
    """
    stale_id = "1" * 26
    stale_raw = storage.save_raw_document(motorbike.id, stale_id, b"<html>old</html>")
    asyncio.run(
        document_service.create_document(
            fake_session,
            motorbike.id,
            document_id=stale_id,
            source_type=SourceType.WIKIPEDIA,
            source_title="Stale article",
            raw_path=stale_raw,
            content_markdown="old",
            fetched_at=operation.created_at,
        )
    )
    listing_id = "3" * 26
    listing_raw = storage.save_raw_document(motorbike.id, listing_id, b"<html>listing</html>")
    asyncio.run(
        document_service.create_document(
            fake_session,
            motorbike.id,
            document_id=listing_id,
            source_type=SourceType.LISTING,
            source_title="Used GSR600 for sale",
            raw_path=listing_raw,
            content_markdown="Asking 4200 EUR, low mileage.",
            fetched_at=operation.created_at,
        )
    )

    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    documents = fake_session.rows(SourceDocument)
    document_ids = {document.id for document in documents}
    # The stale `wikipedia` document is gone, exactly as `test_re_ingestion_
    # replaces_the_documents_and_the_image_of_the_previous_run` proves above —
    # this is the "otherwise untouched" half of the carve-out.
    assert stale_id not in document_ids
    assert not storage.resolve(stale_raw).exists()
    # The `listing` document's row and file both survive the discard.
    assert listing_id in document_ids
    assert storage.resolve(listing_raw).exists()
    listing_document = next(document for document in documents if document.id == listing_id)
    assert listing_document.source_type is SourceType.LISTING
    # Plus the one freshly-fetched Wikipedia document from this run.
    assert len(documents) == 2


# --- suggestion as research input (step 6.17) ----------------------------------


def _stub_extraction_result(monkeypatch: pytest.MonkeyPatch, **fields: Any) -> None:
    """Answer the extraction stage with a fixed, identity-bearing result.

    Unlike the autouse `extracted_specs` fixture (which never sets
    `model_name` and so only exercises the manufacturer-only path), this lets
    a test drive the full `assign_identity` merge and get back real
    `year_from`/`year_to`/`type_codes` on `outcome.extracted`.
    """
    payload: dict[str, Any] = {"model_name": "GSR600", "manufacturer": "Suzuki"}
    payload.update(fields)

    async def extract_spec(name: str, documents: Any, *, model: str | None = None):
        return extraction.ExtractedSpec.model_validate(payload)

    monkeypatch.setattr(extraction, "extract_spec", extract_spec)


def test_suggested_links_are_fetched_before_provider_candidates_and_deduped(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    motorbike.suggestion = {
        "links": [
            "https://suzuki.example/gsr600?utm_source=chatgpt.com",
            "https://claimed.example/gsr600-extra",
        ],
        "type_codes": [],
    }
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(
        monkeypatch,
        search.SearchResults(
            candidates=(
                # Same URL as the first claimed link once cleaned of `utm_source` —
                # the provider's copy must be the one dropped, not the claim's.
                _candidate("https://suzuki.example/gsr600", SourceType.PRODUCT),
                _candidate("https://provider.example/gsr600", SourceType.MAGAZINE),
            )
        ),
    )
    fetched = _stub_fetch(
        monkeypatch,
        {
            "https://suzuki.example/gsr600": _fetch_result("https://suzuki.example/gsr600"),
            "https://claimed.example/gsr600-extra": _fetch_result(
                "https://claimed.example/gsr600-extra"
            ),
            "https://provider.example/gsr600": _fetch_result("https://provider.example/gsr600"),
        },
    )
    _stub_extract(monkeypatch, extract.ExtractResult(markdown="## Data\n\n599 cc."))

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    # Suggested links first, deduped against the provider's duplicate.
    assert fetched == [
        "https://suzuki.example/gsr600",
        "https://claimed.example/gsr600-extra",
        "https://provider.example/gsr600",
    ]
    documents = fake_session.rows(SourceDocument)
    assert [document.source_type for document in documents] == [
        SourceType.WIKIPEDIA,
        SourceType.TECHNICAL,
        SourceType.TECHNICAL,
        SourceType.MAGAZINE,
    ]
    # The stored claim is never modified (D6) — the utm parameter survives there.
    assert (
        motorbike.suggestion["links"][0] == "https://suzuki.example/gsr600?utm_source=chatgpt.com"
    )


def test_claimed_type_codes_add_one_extra_query_template_to_the_provider_call(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    motorbike.suggestion = {"links": [], "type_codes": ["K80", "K81", "K82"]}
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    captured = _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    # Only the first `MAX_TYPE_CODE_TERMS` (2) codes feed the extra template.
    assert captured == [
        (
            *search.QUERY_TEMPLATES,
            search.QueryTemplate(
                SourceType.TECHNICAL, '"{name}" K80 K81 motorcycle specifications'
            ),
        )
    ]


def test_a_row_without_a_suggestion_behaves_byte_identically_to_today(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert motorbike.suggestion is None
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    captured = _stub_search(
        monkeypatch,
        search.SearchResults(
            candidates=(_candidate("https://suzuki.example/gsr600", SourceType.PRODUCT),)
        ),
    )
    _stub_fetch(
        monkeypatch,
        {"https://suzuki.example/gsr600": _fetch_result("https://suzuki.example/gsr600")},
    )
    _stub_extract(monkeypatch, extract.ExtractResult(markdown="## Data\n\n599 cc."))

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert captured == [search.QUERY_TEMPLATES]
    documents = fake_session.rows(SourceDocument)
    assert [document.source_type for document in documents] == [
        SourceType.WIKIPEDIA,
        SourceType.PRODUCT,
    ]
    assert operation.status is OperationStatus.SUCCEEDED


def test_a_contradicted_claimed_year_range_is_warned_about(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    motorbike.suggestion = {"links": [], "type_codes": [], "year_from": 2004, "year_to": 2018}
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())
    _stub_extraction_result(monkeypatch, year_from=2004, year_to=2012)

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.message is not None
    assert (
        service.CLAIM_YEAR_WARNING.format(claimed="2004-2018", found="2004-2012")
        in operation.message
    )


def test_no_year_warning_when_the_finding_matches_the_claim(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    motorbike.suggestion = {"links": [], "type_codes": [], "year_from": 2004, "year_to": 2018}
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())
    _stub_extraction_result(monkeypatch, year_from=2004, year_to=2018)

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.message is not None
    assert "Suggestion contradicted" not in operation.message


def test_a_contradicted_claimed_type_code_is_warned_about(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    motorbike.suggestion = {"links": [], "type_codes": ["K80"]}
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())
    _stub_extraction_result(monkeypatch, type_codes=["ZX9"])

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.message is not None
    assert service.CLAIM_CODE_WARNING.format(claimed="K80", found="ZX9") in operation.message


def test_no_code_warning_when_the_finding_is_a_subset_of_the_claim(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    motorbike.suggestion = {"links": [], "type_codes": ["K80", "K81"]}
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())
    _stub_extraction_result(monkeypatch, type_codes=["K80"])

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.message is not None
    assert "Suggestion contradicted" not in operation.message


def test_identity_warnings_from_extraction_are_fed_to_the_run(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """6.15's `identity_warnings` (dropped type-code/variant entries) reach `_warn`."""
    motorbike.suggestion = None
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())
    # An invalid type code is dropped by `identity_validation.normalize_type_codes`
    # with a warning, without failing the extraction.
    _stub_extraction_result(monkeypatch, type_codes=["not a valid code!"])

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.message is not None
    assert operation.message.startswith(service.WARNING_SUMMARY_PREFIX)
