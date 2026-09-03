"""`GET /api/events` — the SPA's single server-sent event stream.

Plain SSE, deliberately outside the JSON:API layer: the payloads are
notifications, not resources. Each event carries ids only; the browser refetches
through the normal API, which is why a missed event can never mean stale truth
for long.

Authentication is the session cookie (`current_user`) — `EventSource` cannot
send headers, which is why `SameSite=Lax` was frozen in Phase 1. The stream is
open to any signed-in account: it announces that *something* changed, never
what.
"""

import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse, ServerSentEvent

from app.api.deps import current_user
from app.services.notification_listener import NotificationListener

logger = logging.getLogger(__name__)

# Keeps proxies and idle browser connections from timing the stream out.
PING_INTERVAL_SECONDS = 15

# Where the lifespan parks the process' listener.
LISTENER_STATE_ATTRIBUTE = "notification_listener"

router = APIRouter(
    prefix="/events",
    tags=["events"],
    dependencies=[Depends(current_user)],
)


def _listener(request: Request) -> NotificationListener:
    """Return the process' listener, or refuse the stream if there is none."""
    listener = getattr(request.app.state, LISTENER_STATE_ATTRIBUTE, None)
    if listener is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event stream unavailable.",
        )
    return listener


async def _stream(listener: NotificationListener) -> AsyncGenerator[ServerSentEvent]:
    """Yield one SSE message per notification for as long as the client listens."""
    queue = listener.subscribe()
    try:
        while True:
            event = await queue.get()
            yield ServerSentEvent(event=event.name, data=event.data)
    finally:
        # Reached on client disconnect and on shutdown alike, so a closed
        # browser tab never leaves a queue behind for the listener to fill.
        listener.unsubscribe(queue)


@router.get(
    "",
    response_class=EventSourceResponse,
    summary="Subscribe to server-sent events",
    responses={
        status.HTTP_200_OK: {
            "description": "An event stream of `operation.updated`, `product.updated` "
            "and `document.updated` notifications.",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
async def events(request: Request) -> EventSourceResponse:
    """Open the notification stream for the signed-in account."""
    return EventSourceResponse(_stream(_listener(request)), ping=PING_INTERVAL_SECONDS)
