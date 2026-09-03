"""QA coverage for `operation_service` and the `product.updated` emitters wired
in step 2.6, extending `test_operation_service.py` and `test_product_service.py`
rather than duplicating them.

Focus areas the dev suite does not already nail down:

* the `advance()` out-of-range contract (raise, not clamp or 500) and that the
  operation is left untouched when it raises;
* payload size/shape stays ids-only even when `message`/`error` are pushed to
  their column limits (the risk the 1 KB NOTIFY budget actually protects
  against);
* commit-then-notify ordering for `advance`/`fail`, not just `create`/`start`;
* `product_service`'s `product.updated` emissions: shape on creation/legal
  transition/draftSpec PATCH, and — the negative case — that an illegal
  transition or a failed (duplicate-slug) creation notifies nobody.
"""

import asyncio
import json
from typing import Any

import pytest

from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.operation import ERROR_LENGTH, MESSAGE_LENGTH, Operation
from app.services import operation_service, product_service
from app.services.operation_service import EVENT_CHANNEL
from app.services.product_service import DuplicateModelError, InvalidTransitionError
from tests.services.conftest import FakeAsyncSession

NOTIFY_PAYLOAD_LIMIT_BYTES = 1024
OPERATION_PAYLOAD_KEYS = {"event", "operationId", "entityType", "entityId"}
PRODUCT_PAYLOAD_KEYS = {"event", "productId"}


class _RecordingSession(FakeAsyncSession):
    """Mirrors `test_operation_service.py`'s helper: an interleaved commit/notify log."""

    def __init__(self) -> None:
        super().__init__()
        self.log: list[str] = []

    async def commit(self) -> None:
        await super().commit()
        self.log.append("commit")

    async def execute(self, statement: object) -> Any:
        before = len(self.notifications)
        result = await super().execute(statement)
        if len(self.notifications) > before:
            self.log.append("notify")
        return result


@pytest.fixture
def session() -> _RecordingSession:
    return _RecordingSession()


def _create(session: FakeAsyncSession, **kwargs: Any) -> Operation:
    return asyncio.run(operation_service.create(session, "demo", **kwargs))


def _payloads(session: FakeAsyncSession) -> list[dict[str, Any]]:
    return [json.loads(payload) for _channel, payload in session.notifications]


# --- advance(): out-of-range contract ------------------------------------------


@pytest.mark.parametrize("progress", [0, 100])
def test_advance_accepts_the_boundary_values(session: _RecordingSession, progress: int) -> None:
    operation = _create(session)

    updated = asyncio.run(operation_service.advance(session, operation, progress, "Working"))

    assert updated.progress == progress


@pytest.mark.parametrize("progress", [-5, 150])
def test_advance_out_of_range_raises_and_leaves_the_row_untouched(
    session: _RecordingSession, progress: int
) -> None:
    operation = _create(session)
    commits_before = session.commit_count
    notifications_before = len(session.notifications)

    with pytest.raises(ValueError, match="Progress must be between 0 and 100"):
        asyncio.run(operation_service.advance(session, operation, progress, "Working"))

    # Not a silent clamp, not a 500: a clean exception, no partial write, no
    # spurious notification for a change that never happened.
    assert operation.progress == 0
    assert operation.message is None
    assert session.commit_count == commits_before
    assert len(session.notifications) == notifications_before


# --- payload shape/size stays ids-only even at column limits -------------------


def test_advance_payload_excludes_the_message_even_at_the_column_limit(
    session: _RecordingSession,
) -> None:
    operation = _create(session)
    long_message = "m" * MESSAGE_LENGTH

    asyncio.run(operation_service.advance(session, operation, 50, long_message))

    payload = _payloads(session)[-1]
    assert set(payload) == OPERATION_PAYLOAD_KEYS
    assert "message" not in payload
    assert len(json.dumps(payload).encode()) <= NOTIFY_PAYLOAD_LIMIT_BYTES


def test_fail_payload_excludes_the_error_even_at_the_column_limit(
    session: _RecordingSession,
) -> None:
    operation = _create(session)
    long_error = "e" * ERROR_LENGTH

    asyncio.run(operation_service.fail(session, operation, long_error))

    payload = _payloads(session)[-1]
    assert set(payload) == OPERATION_PAYLOAD_KEYS
    assert "error" not in payload
    assert len(json.dumps(payload).encode()) <= NOTIFY_PAYLOAD_LIMIT_BYTES


# --- commit-then-notify ordering, for the two state changes the dev suite's ---
# --- ordering test does not exercise (it only walks create -> start) ----------


def test_advance_commits_before_it_notifies(session: _RecordingSession) -> None:
    operation = _create(session)
    asyncio.run(operation_service.start(session, operation))
    session.log.clear()

    asyncio.run(operation_service.advance(session, operation, 30, "Fetching sources (1/6)"))

    assert session.log == ["commit", "notify", "commit"]


def test_fail_commits_before_it_notifies(session: _RecordingSession) -> None:
    operation = _create(session)
    asyncio.run(operation_service.start(session, operation))
    session.log.clear()

    asyncio.run(operation_service.fail(session, operation, "No usable documents."))

    assert session.log == ["commit", "notify", "commit"]


# --- product_service: product.updated shape and negative cases ----------------


def _backlog(session: FakeAsyncSession, name: str = "Suzuki GSR 600") -> Motorbike:
    return asyncio.run(product_service.create_backlog(session, name))


def test_create_backlog_emits_a_correctly_shaped_product_updated_event(
    session: _RecordingSession,
) -> None:
    motorbike = _backlog(session)

    assert {channel for channel, _ in session.notifications} == {EVENT_CHANNEL}
    payload = _payloads(session)[-1]
    assert set(payload) == PRODUCT_PAYLOAD_KEYS
    assert payload == {"event": "product.updated", "productId": motorbike.id}


def test_duplicate_slug_creation_does_not_notify(session: _RecordingSession) -> None:
    _backlog(session, "Suzuki GSR 600")
    notifications_before = len(session.notifications)

    with pytest.raises(DuplicateModelError):
        _backlog(session, "suzuki gsr-600")

    assert len(session.notifications) == notifications_before


def test_legal_transition_emits_product_updated(session: _RecordingSession) -> None:
    motorbike = _backlog(session)
    session.notifications.clear()

    asyncio.run(product_service.transition(session, motorbike, MotorbikeStatus.INGESTING))

    payload = _payloads(session)[-1]
    assert payload == {"event": "product.updated", "productId": motorbike.id}


def test_illegal_transition_does_not_notify(session: _RecordingSession) -> None:
    motorbike = _backlog(session)
    session.notifications.clear()

    with pytest.raises(InvalidTransitionError):
        asyncio.run(product_service.transition(session, motorbike, MotorbikeStatus.APPROVED))

    assert session.notifications == []


def test_draft_spec_patch_emits_product_updated(session: _RecordingSession) -> None:
    motorbike = _backlog(session)
    session.notifications.clear()

    asyncio.run(product_service.upsert_draft_spec(session, motorbike.id, {"engine_cc": 599}))

    payload = _payloads(session)[-1]
    assert payload == {"event": "product.updated", "productId": motorbike.id}
