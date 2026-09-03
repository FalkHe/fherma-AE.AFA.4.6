"""`app/services/notification_listener.py` — fan-out, cleanup and reconnect.

No database: a stub stands in for the psycopg connection through the listener's
injectable connection factory. Coroutines are driven with `asyncio.run()` per
the project's "no pytest-asyncio" convention, so every scenario is one async
function executed inside a single test.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import pytest
from psycopg import sql

from app.services import notification_listener
from app.services.notification_listener import (
    SUBSCRIBER_QUEUE_SIZE,
    Event,
    EventQueue,
    NotificationListener,
)

OPERATION_PAYLOAD = json.dumps(
    {
        "event": "operation.updated",
        "operationId": "01OPERATION",
        "entityType": "motorbike",
        "entityId": "01BIKE",
    }
)
PRODUCT_PAYLOAD = json.dumps({"event": "product.updated", "productId": "01BIKE"})

# How long a test waits for the listener before declaring the fan-out broken.
TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class _Notification:
    """The one attribute the listener reads off a psycopg `Notify`."""

    payload: str


class _StubConnection:
    """Stand-in for a psycopg `AsyncConnection` in LISTEN mode."""

    def __init__(self, payloads: list[str]) -> None:
        self.payloads = payloads
        self.statements: list[str] = []
        self.delivered = False
        self.closed = False

    async def __aenter__(self) -> "_StubConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        self.closed = True
        return False

    async def execute(self, statement: sql.Composable) -> None:
        self.statements.append(statement.as_string())

    async def notifies(self) -> AsyncIterator[_Notification]:
        """Deliver the configured payloads, then stay connected like a real one."""
        for payload in self.payloads:
            yield _Notification(payload)
        self.delivered = True
        await asyncio.Event().wait()


def _factory(*connections: object) -> Callable[[], Awaitable[object]]:
    """Return a connection factory handing out `connections` in order.

    An exception stands in for a failed connection attempt; running out means
    the listener reconnected more often than the scenario expected.
    """
    remaining = list(connections)

    async def connect() -> object:
        assert remaining, "The listener asked for more connections than expected."
        candidate = remaining.pop(0)
        if isinstance(candidate, BaseException):
            raise candidate
        return candidate

    return connect


async def _next(queue: EventQueue) -> Event:
    """Await the next event on `queue`, failing the test instead of hanging."""
    return await asyncio.wait_for(queue.get(), TIMEOUT_SECONDS)


async def _until(reached: Callable[[], bool]) -> None:
    """Hand control to the listener task until `reached()` holds."""

    async def spin() -> None:
        while not reached():
            await asyncio.sleep(0)

    await asyncio.wait_for(spin(), TIMEOUT_SECONDS)


def test_every_subscriber_receives_every_event() -> None:
    """One notification is framed once and delivered to all open streams."""

    async def scenario() -> tuple[list[Event], list[Event], list[str]]:
        connection = _StubConnection([OPERATION_PAYLOAD, PRODUCT_PAYLOAD])
        listener = NotificationListener(_factory(connection))
        first, second = listener.subscribe(), listener.subscribe()
        listener.start()
        try:
            return (
                [await _next(first), await _next(first)],
                [await _next(second), await _next(second)],
                connection.statements,
            )
        finally:
            await listener.stop()

    first, second, statements = asyncio.run(scenario())

    assert first == second
    assert [event.name for event in first] == ["operation.updated", "product.updated"]
    assert [event.data for event in first] == [OPERATION_PAYLOAD, PRODUCT_PAYLOAD]
    assert statements == ['LISTEN "app_events"']


def test_unusable_payloads_are_dropped_without_breaking_the_stream() -> None:
    """Malformed payloads are a bug elsewhere; the listener keeps running."""

    async def scenario() -> Event:
        connection = _StubConnection(
            ["not json", json.dumps({"productId": "01BIKE"}), "[]", PRODUCT_PAYLOAD]
        )
        listener = NotificationListener(_factory(connection))
        queue = listener.subscribe()
        listener.start()
        try:
            return await _next(queue)
        finally:
            await listener.stop()

    event = asyncio.run(scenario())

    assert (event.name, event.data) == ("product.updated", PRODUCT_PAYLOAD)


def test_an_unsubscribed_queue_stops_being_filled() -> None:
    """A disconnected stream's queue leaves the registry immediately."""

    async def scenario() -> tuple[int, int, int]:
        connection = _StubConnection([PRODUCT_PAYLOAD])
        listener = NotificationListener(_factory(connection))
        gone, watching = listener.subscribe(), listener.subscribe()
        attached = listener.subscriber_count
        listener.unsubscribe(gone)
        # Idempotent: the disconnect and the shutdown path both call it.
        listener.unsubscribe(gone)
        listener.start()
        try:
            # The still-attached stream proves the payload really was fanned out.
            await _next(watching)
            return attached, listener.subscriber_count, gone.qsize()
        finally:
            await listener.stop()

    assert asyncio.run(scenario()) == (2, 1, 0)


def test_stopping_cancels_the_task_and_closes_the_connection() -> None:
    """Shutdown leaves no pending task, no open connection and no queues behind."""

    async def scenario() -> tuple[int, bool]:
        connection = _StubConnection([])
        listener = NotificationListener(_factory(connection))
        listener.subscribe()
        listener.start()
        await _until(lambda: connection.delivered)
        await listener.stop()
        # Stopping twice must not fail: teardown runs after a startup that may
        # itself have failed halfway.
        await listener.stop()
        return listener.subscriber_count, connection.closed

    assert asyncio.run(scenario()) == (0, True)


def test_a_failed_connection_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dead database costs events, not the listener: it reconnects and resumes."""
    monkeypatch.setattr(notification_listener, "INITIAL_RECONNECT_DELAY_SECONDS", 0.0)

    async def scenario() -> tuple[Event, list[str]]:
        connection = _StubConnection([PRODUCT_PAYLOAD])
        listener = NotificationListener(_factory(OSError("connection refused"), connection))
        queue = listener.subscribe()
        listener.start()
        try:
            return await _next(queue), connection.statements
        finally:
            await listener.stop()

    event, statements = asyncio.run(scenario())

    assert event.name == "product.updated"
    # The reconnect re-issues the LISTEN — a silent connection would be worse
    # than a broken one.
    assert statements == ['LISTEN "app_events"']


def test_a_client_that_stops_reading_only_loses_its_oldest_events() -> None:
    """A full subscriber queue never blocks the listener."""
    overflow = 3

    async def scenario() -> list[Event]:
        payloads = [
            json.dumps({"event": f"product.updated.{index}", "productId": "01BIKE"})
            for index in range(SUBSCRIBER_QUEUE_SIZE + overflow)
        ]
        connection = _StubConnection(payloads)
        listener = NotificationListener(_factory(connection))
        queue = listener.subscribe()
        listener.start()
        try:
            await _until(lambda: connection.delivered)
            return [await _next(queue) for _ in range(queue.qsize())]
        finally:
            await listener.stop()

    events = asyncio.run(scenario())

    assert len(events) == SUBSCRIBER_QUEUE_SIZE
    # The newest events survived; the oldest ones were discarded.
    assert events[0].name == f"product.updated.{overflow}"
    assert events[-1].name == f"product.updated.{SUBSCRIBER_QUEUE_SIZE + overflow - 1}"
