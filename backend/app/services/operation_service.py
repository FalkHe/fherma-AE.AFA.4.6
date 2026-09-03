"""Operations: the lifecycle of a tracked job and the `app_events` publisher.

Two things live here, and the second one is used well beyond operations:

* the operation lifecycle — `create` (queued) → `start` → `advance` →
  `succeed` | `fail` — each step its own transaction, because a progress tick
  must be visible to the admin UI while the job is still running;
* `notify`, the single place that writes to the PostgreSQL `app_events`
  channel. Every emitter in the project goes through it, so the pinned
  ordering rule holds everywhere: **commit first, then `pg_notify`.**

Why that order matters: `NOTIFY` is delivered when *its* transaction commits.
Publishing inside the data transaction would let a listener refetch before the
data is visible — or announce a change that then rolls back. Committing the
data first and publishing afterwards can only lose an event (the SSE hook
recovers by invalidating on reconnect), never invent one.

Payloads carry **ids only, never content**: the channel has an 8 KB limit and
clients refetch through the API anyway.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.operation import (
    ERROR_LENGTH,
    MAX_PROGRESS,
    MESSAGE_LENGTH,
    MIN_PROGRESS,
    Operation,
    OperationStatus,
)

# The one channel every event of this application travels on.
EVENT_CHANNEL = "app_events"

# `entity_type` of an operation working on a catalogue row. The admin backlog
# joins its progress cells on (this, motorbike id).
MOTORBIKE_ENTITY_TYPE = "motorbike"

# `entity_type` of an operation answering a consultation turn. The chat UI reads
# it off the `operation.updated` event to know an event concerns a conversation.
CHAT_ENTITY_TYPE = "chat"


async def notify(session: AsyncSession, payload: Mapping[str, Any]) -> None:
    """Publish `payload` on `app_events` — call this **after** the commit.

    Issues the `pg_notify` and commits it, so the notification is on its way by
    the time this returns. Callers therefore never own a transaction across it.
    """
    encoded = json.dumps(payload, separators=(",", ":"))
    await session.execute(select(func.pg_notify(EVENT_CHANNEL, encoded)))
    await session.commit()


async def create(
    session: AsyncSession,
    type: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> Operation:
    """Create a `queued` operation of `type` and announce it.

    The row is created *before* the task is enqueued, so a job can never run
    without a row to report into.
    """
    operation = Operation(
        type=type,
        status=OperationStatus.QUEUED,
        progress=MIN_PROGRESS,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    session.add(operation)
    await session.commit()
    await _announce(session, operation)
    return operation


async def get(session: AsyncSession, operation_id: str) -> Operation | None:
    """Return one operation, or `None` when the id is unknown.

    The worker needs this: a task is enqueued with an operation id and reloads
    the row in its own session before it starts reporting into it.
    """
    result = await session.execute(select(Operation).where(Operation.id == operation_id))
    return result.scalar_one_or_none()


async def start(session: AsyncSession, operation: Operation) -> Operation:
    """Mark `operation` as `running` and stamp `started_at`."""
    operation.status = OperationStatus.RUNNING
    operation.started_at = datetime.now(UTC)
    return await _save(session, operation)


async def advance(
    session: AsyncSession, operation: Operation, progress: int, message: str | None = None
) -> Operation:
    """Report a progress milestone; the status is left untouched.

    Raises:
        ValueError: `progress` is outside 0–100 (a caller bug, not user input).
    """
    if not MIN_PROGRESS <= progress <= MAX_PROGRESS:
        raise ValueError(f"Progress must be between {MIN_PROGRESS} and {MAX_PROGRESS}: {progress}.")

    operation.progress = progress
    operation.message = _truncated(message, MESSAGE_LENGTH)
    return await _save(session, operation)


async def succeed(session: AsyncSession, operation: Operation) -> Operation:
    """Mark `operation` as `succeeded`, complete and finished."""
    operation.status = OperationStatus.SUCCEEDED
    operation.progress = MAX_PROGRESS
    operation.finished_at = datetime.now(UTC)
    return await _save(session, operation)


async def fail(session: AsyncSession, operation: Operation, error: str) -> Operation:
    """Mark `operation` as `failed`, keeping `error` for the admin to read.

    `progress` is deliberately left where it stopped: how far a job got is part
    of the diagnosis.
    """
    operation.status = OperationStatus.FAILED
    operation.error = _truncated(error, ERROR_LENGTH)
    operation.finished_at = datetime.now(UTC)
    return await _save(session, operation)


async def list_operations(
    session: AsyncSession,
    *,
    entity_types: Sequence[str] | None = None,
    entity_ids: Sequence[str] | None = None,
    statuses: Sequence[OperationStatus] | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Operation], int]:
    """Return one page of operations plus the unpaginated total.

    Newest first (`created_at` descending, id as tiebreaker so paging is stable
    for rows created in the same instant). Every filter is a set of accepted
    values; `None` means unfiltered.
    """
    conditions = []
    if entity_types:
        conditions.append(Operation.entity_type.in_(list(entity_types)))
    if entity_ids:
        conditions.append(Operation.entity_id.in_(list(entity_ids)))
    if statuses:
        conditions.append(Operation.status.in_(list(statuses)))

    total = await session.execute(select(func.count()).select_from(Operation).where(*conditions))
    page = await session.execute(
        select(Operation)
        .where(*conditions)
        .order_by(Operation.created_at.desc(), Operation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(page.scalars().all()), total.scalar_one()


async def _save(session: AsyncSession, operation: Operation) -> Operation:
    """Commit a state change, then announce it."""
    await session.commit()
    # `operations.updated_at` has a server-side `onupdate`, so the flush expires
    # the attribute; reading it back later would be implicit IO — fatal on an
    # async session. One refresh hands callers a fully loaded row.
    await session.refresh(operation)
    await _announce(session, operation)
    return operation


async def _announce(session: AsyncSession, operation: Operation) -> None:
    """Publish the pinned `operation.updated` payload — ids only."""
    await notify(
        session,
        {
            "event": "operation.updated",
            "operationId": operation.id,
            "entityType": operation.entity_type,
            "entityId": operation.entity_id,
        },
    )


def _truncated(value: str | None, length: int) -> str | None:
    """Cut `value` to what its column holds; an over-long message is not fatal."""
    return None if value is None else value[:length]
