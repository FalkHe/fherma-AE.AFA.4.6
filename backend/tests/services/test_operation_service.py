"""`app/services/operation_service.py` — lifecycle and the `app_events` publisher.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.

The ordering rule — commit first, then `pg_notify` — is the one thing here that
cannot be checked by looking at the result, so `_RecordingSession` keeps an
interleaved log of commits and notifications.
"""

import asyncio
import json
from typing import Any

import pytest

from app.db.models.operation import ERROR_LENGTH, MESSAGE_LENGTH, Operation, OperationStatus
from app.services import operation_service
from app.services.operation_service import EVENT_CHANNEL, MOTORBIKE_ENTITY_TYPE
from tests.services.conftest import FakeAsyncSession

BIKE_ID = "0" * 22 + "BIKE"


class _RecordingSession(FakeAsyncSession):
    """A fake session that also remembers the *order* of commits and notifies."""

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


def _payloads(session: FakeAsyncSession) -> list[dict[str, Any]]:
    """Return the decoded payloads published on the events channel."""
    return [json.loads(payload) for channel, payload in session.notifications]


def _create(session: FakeAsyncSession, **kwargs: Any) -> Operation:
    return asyncio.run(operation_service.create(session, "demo", **kwargs))


# --- lifecycle ----------------------------------------------------------------


def test_create_stores_a_queued_operation(session: _RecordingSession) -> None:
    operation = _create(session)

    assert session.rows(Operation) == [operation]
    assert operation.status is OperationStatus.QUEUED
    assert operation.progress == 0
    assert operation.message is None
    assert operation.error is None
    assert (operation.started_at, operation.finished_at) == (None, None)


def test_create_links_the_entity_when_given(session: _RecordingSession) -> None:
    operation = _create(session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)

    assert (operation.entity_type, operation.entity_id) == (MOTORBIKE_ENTITY_TYPE, BIKE_ID)


def test_create_leaves_the_entity_unset_by_default(session: _RecordingSession) -> None:
    operation = _create(session)

    assert (operation.entity_type, operation.entity_id) == (None, None)


def test_start_marks_the_operation_running_and_stamps_started_at(
    session: _RecordingSession,
) -> None:
    operation = _create(session)

    asyncio.run(operation_service.start(session, operation))

    assert operation.status is OperationStatus.RUNNING
    assert operation.started_at is not None
    assert operation.finished_at is None


def test_advance_reports_progress_without_touching_the_status(
    session: _RecordingSession,
) -> None:
    operation = _create(session)
    asyncio.run(operation_service.start(session, operation))

    asyncio.run(operation_service.advance(session, operation, 40, "Fetching sources (3/6)"))

    assert operation.status is OperationStatus.RUNNING
    assert operation.progress == 40
    assert operation.message == "Fetching sources (3/6)"


@pytest.mark.parametrize("progress", [-1, 101])
def test_advance_rejects_progress_outside_the_percentage_range(
    session: _RecordingSession, progress: int
) -> None:
    operation = _create(session)

    with pytest.raises(ValueError, match="Progress must be between 0 and 100"):
        asyncio.run(operation_service.advance(session, operation, progress, "Working"))


def test_advance_truncates_an_over_long_message(session: _RecordingSession) -> None:
    operation = _create(session)

    asyncio.run(operation_service.advance(session, operation, 10, "x" * (MESSAGE_LENGTH + 50)))

    assert operation.message == "x" * MESSAGE_LENGTH


def test_succeed_completes_the_operation(session: _RecordingSession) -> None:
    operation = _create(session)
    asyncio.run(operation_service.start(session, operation))
    asyncio.run(operation_service.advance(session, operation, 90, "Generating embeddings"))

    asyncio.run(operation_service.succeed(session, operation))

    assert operation.status is OperationStatus.SUCCEEDED
    assert operation.progress == 100
    assert operation.finished_at is not None
    assert operation.error is None


def test_fail_records_the_error_and_keeps_the_progress_reached(
    session: _RecordingSession,
) -> None:
    operation = _create(session)
    asyncio.run(operation_service.start(session, operation))
    asyncio.run(operation_service.advance(session, operation, 15, "Searching the web"))

    asyncio.run(operation_service.fail(session, operation, "No usable documents."))

    assert operation.status is OperationStatus.FAILED
    assert operation.error == "No usable documents."
    assert operation.progress == 15
    assert operation.finished_at is not None


def test_fail_truncates_an_over_long_error(session: _RecordingSession) -> None:
    operation = _create(session)

    asyncio.run(operation_service.fail(session, operation, "e" * (ERROR_LENGTH + 50)))

    assert operation.error == "e" * ERROR_LENGTH


# --- events -------------------------------------------------------------------


def test_every_state_change_publishes_one_ids_only_payload(session: _RecordingSession) -> None:
    operation = _create(session, entity_type=MOTORBIKE_ENTITY_TYPE, entity_id=BIKE_ID)
    asyncio.run(operation_service.start(session, operation))
    asyncio.run(operation_service.advance(session, operation, 65, "Processing images"))
    asyncio.run(operation_service.succeed(session, operation))

    assert {channel for channel, _ in session.notifications} == {EVENT_CHANNEL}
    payloads = _payloads(session)
    assert len(payloads) == 4
    assert all(
        payload
        == {
            "event": "operation.updated",
            "operationId": operation.id,
            "entityType": MOTORBIKE_ENTITY_TYPE,
            "entityId": BIKE_ID,
        }
        for payload in payloads
    )
    # Ids only: no message, progress or status rides on the channel.
    assert all(len(json.dumps(payload).encode()) <= 1024 for payload in payloads)


def test_a_failure_publishes_the_same_payload_shape(session: _RecordingSession) -> None:
    operation = _create(session)

    asyncio.run(operation_service.fail(session, operation, "boom"))

    assert _payloads(session)[-1] == {
        "event": "operation.updated",
        "operationId": operation.id,
        "entityType": None,
        "entityId": None,
    }


def test_notification_always_follows_the_commit_it_announces(
    session: _RecordingSession,
) -> None:
    operation = _create(session)
    asyncio.run(operation_service.start(session, operation))

    # Per state change: the data commit, the notify, and the commit that
    # delivers it — never a notify before the commit it belongs to.
    assert session.log == ["commit", "notify", "commit"] * 2
    assert session.log.index("commit") < session.log.index("notify")


def test_notify_publishes_a_payload_on_the_pinned_channel(session: _RecordingSession) -> None:
    asyncio.run(operation_service.notify(session, {"event": "product.updated", "productId": "abc"}))

    assert session.notifications == [
        (EVENT_CHANNEL, '{"event":"product.updated","productId":"abc"}')
    ]
    assert session.log == ["notify", "commit"]
