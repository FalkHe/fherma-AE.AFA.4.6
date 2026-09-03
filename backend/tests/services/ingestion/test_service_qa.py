"""QA coverage for the ingestion orchestration service (step 2.14).

Extends `test_service.py` rather than duplicating it. That suite already
proves the milestone sequence, the partial-failure rule, the zero-document
failure path and fresh-run replacement with mocked adapters — this file adds
the assertions the dev suite leaves implicit:

* operation `started_at`/`finished_at` are actually stamped, not just the
  status/progress fields;
* the zero-document failure path really announces `product.updated` (the bike
  flipping back to `backlog` must be visible to a listening admin, not just
  true in the row);
* the transient/deterministic boundary also holds for a *fetch* failure
  reason, not only a Wikipedia one — the dev suite only drives the boundary
  through `wikipedia.WikipediaFailureReason`;
* status flips are proven to ride `product_service.transition` itself (never
  a direct `motorbike.status = …` write) by spying on the real function;
* a *missing* image (no lead image found at all) is silent — no warning, no
  failure — distinct from the dev suite's "image download failed" case.

Adapter stubs are imported from `test_service.py` rather than re-declared, per
its own docstring's "extend, don't duplicate" instruction. The `motorbike`,
`operation` and `data_directories` fixtures are small enough (and importing a
pytest fixture under its exact parameter name trips ruff's F811 on every test
that requests it) that they are reconstructed locally instead, exactly as
`test_service.py` builds them.
"""

import asyncio
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.operation import Operation, OperationStatus
from app.jobs import TransientJobError
from app.services import operation_service, product_service
from app.services.ingestion import fetch, search, service, wikipedia
from tests.services.conftest import FakeAsyncSession
from tests.services.ingestion.test_service import (
    CLIENT,
    MODEL_NAME,
    WIKIPEDIA_IMAGE,
    _candidate,
    _stub_fetch,
    _stub_search,
    _stub_wikipedia,
    _wikipedia_result,
)


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


def _payloads(session: FakeAsyncSession) -> list[dict[str, Any]]:
    return [json.loads(payload) for _channel, payload in session.notifications]


# --- criterion 1: operation timestamps -----------------------------------------


def test_successful_run_stamps_started_at_and_finished_at(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert operation.started_at is None
    assert operation.finished_at is None

    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.started_at is not None
    assert operation.finished_at is not None
    assert operation.finished_at >= operation.started_at


def test_deterministic_failure_also_stamps_started_at_and_finished_at(
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
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.FAILED
    assert operation.started_at is not None
    assert operation.finished_at is not None


# --- criterion 2: zero-document failure really announces product.updated ------


def test_zero_documents_failure_announces_product_updated(
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
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.FAILED
    assert motorbike.status is MotorbikeStatus.BACKLOG

    product_events = [
        payload for payload in _payloads(fake_session) if payload["event"] == "product.updated"
    ]
    # The transition to `backlog` (job-failure path) is the last one announced.
    assert product_events[-1] == {"event": "product.updated", "productId": motorbike.id}
    # And the operation's own state change is announced too — an admin watching
    # only the operations feed still learns the run is over.
    operation_events = [
        payload for payload in _payloads(fake_session) if payload["event"] == "operation.updated"
    ]
    assert operation_events[-1]["operationId"] == operation.id


def test_successful_run_announces_product_updated_on_the_in_review_flip(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    product_events = [
        payload for payload in _payloads(fake_session) if payload["event"] == "product.updated"
    ]
    assert {"event": "product.updated", "productId": motorbike.id} in product_events


# --- criterion 3: transient/deterministic boundary also holds at the fetch layer


def test_a_transient_fetch_reason_on_the_only_candidate_raises_transient_error(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wikipedia found nothing (deterministic) *and* the sole search candidate
    failed for a network reason (transient) — the run must still be retried:
    the boundary is evaluated per source, not just for Wikipedia."""
    _stub_wikipedia(
        monkeypatch,
        wikipedia.WikipediaFailure(
            reason=wikipedia.WikipediaFailureReason.NO_MATCH,
            detail=f"No Wikipedia article matched {MODEL_NAME!r}.",
        ),
    )
    _stub_search(
        monkeypatch,
        search.SearchResults(
            candidates=(_candidate("https://slow.example/gsr600", search.SourceType.PRODUCT),)
        ),
    )
    _stub_fetch(
        monkeypatch,
        {
            "https://slow.example/gsr600": fetch.FetchFailure(
                url="https://slow.example/gsr600",
                reason=fetch.FetchFailureReason.NETWORK_ERROR,
                detail="Network error fetching https://slow.example/gsr600.",
            )
        },
    )

    with pytest.raises(TransientJobError):
        asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.RUNNING
    assert motorbike.status is MotorbikeStatus.INGESTING


def test_a_deterministic_fetch_reason_on_the_only_candidate_fails_without_retry(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mirror case: an HTTP 404 on the sole candidate is not worth retrying
    identically, so together with a Wikipedia miss the run fails deterministically."""
    _stub_wikipedia(
        monkeypatch,
        wikipedia.WikipediaFailure(
            reason=wikipedia.WikipediaFailureReason.NO_MATCH,
            detail=f"No Wikipedia article matched {MODEL_NAME!r}.",
        ),
    )
    _stub_search(
        monkeypatch,
        search.SearchResults(
            candidates=(_candidate("https://dead.example/gsr600", search.SourceType.PRODUCT),)
        ),
    )
    _stub_fetch(
        monkeypatch,
        {
            "https://dead.example/gsr600": fetch.FetchFailure(
                url="https://dead.example/gsr600",
                reason=fetch.FetchFailureReason.HTTP_ERROR,
                detail="https://dead.example/gsr600 answered HTTP 404.",
            )
        },
    )

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.FAILED
    assert motorbike.status is MotorbikeStatus.BACKLOG


# --- criterion 6: status flips really ride product_service.transition ---------


def test_success_and_failure_paths_both_go_through_product_service_transition(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_transition = product_service.transition
    calls: list[MotorbikeStatus] = []

    async def spy(session, bike, new_status):
        calls.append(new_status)
        return await real_transition(session, bike, new_status)

    monkeypatch.setattr(product_service, "transition", spy)
    _stub_wikipedia(monkeypatch, _wikipedia_result())
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert calls == [MotorbikeStatus.IN_REVIEW]
    assert motorbike.status is MotorbikeStatus.IN_REVIEW


def test_failure_path_flips_status_through_product_service_transition(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_transition = product_service.transition
    calls: list[MotorbikeStatus] = []

    async def spy(session, bike, new_status):
        calls.append(new_status)
        return await real_transition(session, bike, new_status)

    monkeypatch.setattr(product_service, "transition", spy)
    _stub_wikipedia(
        monkeypatch,
        wikipedia.WikipediaFailure(
            reason=wikipedia.WikipediaFailureReason.NO_MATCH,
            detail=f"No Wikipedia article matched {MODEL_NAME!r}.",
        ),
    )
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert calls == [MotorbikeStatus.BACKLOG]
    assert motorbike.status is MotorbikeStatus.BACKLOG


# --- criterion 7: a missing image (none found) is silent, not even a warning --


def test_no_lead_image_found_is_silent_not_a_warning(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct from `image_service.ingest_image` failing (already covered by
    `test_a_failing_image_is_a_warning_not_a_failure`): here Wikipedia simply
    had no lead image to offer, so the image stage has nothing to attempt at
    all — no warning text, no failure, a clean success."""
    _stub_wikipedia(monkeypatch, _wikipedia_result(image=None))
    _stub_search(monkeypatch, search.SearchResults())

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    # No warnings were collected at all, so the final message carries none of
    # the "Completed with warnings" wording.
    assert operation.message is not None
    assert not operation.message.startswith(service.WARNING_SUMMARY_PREFIX)


def test_a_failing_image_download_does_not_prevent_notifying_the_success(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Complements the dev suite's image-failure test with the notification
    angle: the run still ends by announcing `product.updated` for the
    `in_review` flip, warning notwithstanding."""
    from app.services import image_service

    _stub_wikipedia(monkeypatch, _wikipedia_result(image=WIKIPEDIA_IMAGE))
    _stub_search(monkeypatch, search.SearchResults())

    async def failing_ingest_image(session, motorbike_id, image_url, attribution=None, **kwargs):
        return image_service.ImageFailure(
            url=image_url,
            reason=image_service.ImageFailureReason.DOWNLOAD_FAILED,
            detail="Timed out downloading the image.",
        )

    monkeypatch.setattr(image_service, "ingest_image", failing_ingest_image)

    asyncio.run(service.ingest(fake_session, motorbike, operation, client=CLIENT))

    assert operation.status is OperationStatus.SUCCEEDED
    product_events = [
        payload for payload in _payloads(fake_session) if payload["event"] == "product.updated"
    ]
    assert {"event": "product.updated", "productId": motorbike.id} in product_events
