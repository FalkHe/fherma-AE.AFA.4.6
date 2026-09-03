"""The `app_events` LISTEN loop: PostgreSQL notifications → in-process fan-out.

One background task per web process holds a **dedicated** psycopg connection
and does nothing but `LISTEN app_events`. It never borrows a pooled session:
a `LISTEN` occupies its connection for the process' whole lifetime, and the
async engine's pool is shared per event loop (see the engine/event-loop
pitfalls in `docs/qa-checklist.md`).

Everything it receives is handed to an in-process registry of subscriber
queues — one queue per open `GET /api/events` stream. The loop therefore does
no I/O towards clients: a slow browser can never stall the listener, it only
loses its own oldest events (payloads are ids, clients refetch, so a gap costs
nothing but a refetch).

The connection is expected to die (database restart, network blip); the loop
reconnects with exponential backoff and re-issues the `LISTEN`. A listener
outage degrades live updates only — the HTTP app stays healthy and ready.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.session import CONNECT_TIMEOUT_SECONDS
from app.services.operation_service import EVENT_CHANNEL

logger = logging.getLogger(__name__)

# Reconnect backoff: quick enough that a database restart is barely noticed,
# capped so a longer outage does not hammer the server.
INITIAL_RECONNECT_DELAY_SECONDS = 1.0
MAX_RECONNECT_DELAY_SECONDS = 30.0

# Per-subscriber buffer. Reached only if a client stops reading its stream.
SUBSCRIBER_QUEUE_SIZE = 100


@dataclass(frozen=True, slots=True)
class Event:
    """One notification, ready to be framed as SSE.

    `name` is the payload's `event` member (the SSE `event:` field), `data` the
    payload JSON verbatim as PostgreSQL delivered it (the SSE `data:` field).
    """

    name: str
    data: str


type EventQueue = asyncio.Queue[Event]

# Returns a psycopg `AsyncConnection`; injectable so tests can drive the loop
# with a stub connection instead of a database.
type ConnectionFactory = Callable[[], Awaitable[Any]]


class NotificationListener:
    """Owns the LISTEN task and the set of subscriber queues."""

    def __init__(
        self,
        connect: ConnectionFactory | None = None,
        *,
        channel: str = EVENT_CHANNEL,
    ) -> None:
        self._connect = connect if connect is not None else _connect
        self._channel = channel
        self._subscribers: set[EventQueue] = set()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Spawn the LISTEN task; starting an already started listener is a no-op.

        Deliberately synchronous: startup must not wait for the database, so a
        database that is still booting cannot delay or fail application startup.
        """
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._listen_forever(), name="app-events-listener")

    async def stop(self) -> None:
        """Cancel the LISTEN task, wait for it to unwind and drop all subscribers."""
        task, self._task = self._task, None
        self._subscribers.clear()
        if task is None:
            return

        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    def subscribe(self) -> EventQueue:
        """Register a new stream and return the queue its events arrive on."""
        queue: EventQueue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: EventQueue) -> None:
        """Drop a stream's queue; safe to call twice (disconnect paths overlap)."""
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        """How many streams are currently attached."""
        return len(self._subscribers)

    async def _listen_forever(self) -> None:
        """Connect, LISTEN, fan out — and reconnect for as long as the process lives."""
        delay = INITIAL_RECONNECT_DELAY_SECONDS
        while True:
            try:
                connection = await self._connect()
                async with connection:
                    await connection.execute(
                        sql.SQL("LISTEN {}").format(sql.Identifier(self._channel))
                    )
                    delay = INITIAL_RECONNECT_DELAY_SECONDS
                    logger.info("Listening for notifications on %s.", self._channel)
                    async for notification in connection.notifies():
                        self._fan_out(notification.payload)
                logger.warning("The %s notification stream ended.", self._channel)
            except asyncio.CancelledError:
                logger.info("Stopped listening on %s.", self._channel)
                raise
            except Exception:
                logger.warning(
                    "Lost the %s listener connection; retrying in %.0fs.",
                    self._channel,
                    delay,
                    exc_info=True,
                )

            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RECONNECT_DELAY_SECONDS)

    def _fan_out(self, payload: str | None) -> None:
        """Parse one payload and offer it to every subscriber."""
        event = _parse(payload)
        if event is None:
            return

        for queue in self._subscribers:
            _offer(queue, event)


def _parse(payload: str | None) -> Event | None:
    """Turn a NOTIFY payload into an `Event`, or `None` if it is unusable.

    Only `notify()` writes this channel, so anything malformed is a bug
    elsewhere: it is logged and dropped rather than killing the listener.
    """
    try:
        decoded = json.loads(payload or "")
    except json.JSONDecodeError:
        logger.warning("Discarding a non-JSON %s payload.", EVENT_CHANNEL)
        return None

    name = decoded.get("event") if isinstance(decoded, dict) else None
    if not isinstance(name, str) or not name:
        logger.warning("Discarding an %s payload without an event name.", EVENT_CHANNEL)
        return None

    return Event(name=name, data=payload or "")


def _offer(queue: EventQueue, event: Event) -> None:
    """Enqueue without ever blocking the listener on a subscriber."""
    if queue.full():
        # A client that stopped reading loses its oldest event instead of
        # blocking everyone else; the newest state is what matters.
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()

    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(event)


async def _connect() -> psycopg.AsyncConnection[Any]:
    """Open the dedicated listener connection from the configured database URL.

    The URL is SQLAlchemy-shaped (`postgresql+psycopg://…`); psycopg wants the
    plain libpq form. `autocommit` is required: `LISTEN` only takes effect when
    its transaction commits.
    """
    url = make_url(get_settings().database_url).set(drivername="postgresql")
    return await psycopg.AsyncConnection.connect(
        url.render_as_string(hide_password=False),
        autocommit=True,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
    )
