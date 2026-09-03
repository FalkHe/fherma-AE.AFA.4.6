"""Used-price snapshots: reads, full-object-replace writes, and the staleness clock.

`motorbike_used_prices` holds at most one row per motorbike (D9) — a research
run either produces a median and replaces the whole row, or it produces
nothing and writes nothing. Nothing here reads the network or reads/writes any
other table; 6.21/6.22 are the writers, 6.23 the reader wired to the estimator
and the API. `is_stale` is computed here, at read time, so the snapshot
(`is_stale` included) is the estimator's reproducible-given-its-inputs input
(D10) rather than something it recomputes on its own.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.motorbike_used_price import MotorbikeUsedPrice
from app.services import operation_service


@dataclass(frozen=True, slots=True)
class UsedPriceSnapshot:
    """A read-side view of one motorbike's used-price row, staleness resolved."""

    motorbike_id: str
    price_min_eur: int
    price_max_eur: int
    price_median_eur: int
    sample_count: int | None
    as_of: datetime
    sources: list[dict[str, Any]]
    is_stale: bool


def is_stale(as_of: datetime, *, now: datetime | None = None) -> bool:
    """Return whether `as_of` is older than `USED_PRICE_MAX_AGE_DAYS` (D10).

    Strict `>`: a snapshot exactly `USED_PRICE_MAX_AGE_DAYS` old is not stale.
    """
    reference = now if now is not None else datetime.now(UTC)
    max_age = timedelta(days=get_settings().used_price_max_age_days)
    return (reference - as_of) > max_age


async def get_snapshot(session: AsyncSession, motorbike_id: str) -> UsedPriceSnapshot | None:
    """Return `motorbike_id`'s used-price snapshot, or `None` if it has none."""
    row = await _get_row(session, motorbike_id)
    if row is None:
        return None
    return _to_snapshot(row)


async def upsert_snapshot(
    session: AsyncSession,
    motorbike_id: str,
    *,
    price_min_eur: int,
    price_max_eur: int,
    price_median_eur: int,
    sample_count: int | None,
    as_of: datetime,
    sources: list[dict[str, Any]],
) -> MotorbikeUsedPrice:
    """Full-object replace the one used-price row of `motorbike_id` (D9).

    Creates the row when none exists yet. Commits, then announces
    `product.updated` — same after-commit ordering rule as
    `product_service._announce` (the catalogue detail renders the snapshot).
    """
    row = await _get_row(session, motorbike_id)
    if row is None:
        row = MotorbikeUsedPrice(motorbike_id=motorbike_id)
        session.add(row)

    row.price_min_eur = price_min_eur
    row.price_max_eur = price_max_eur
    row.price_median_eur = price_median_eur
    row.sample_count = sample_count
    row.as_of = as_of
    row.sources = list(sources)

    await session.commit()
    await _announce(session, motorbike_id)
    return row


async def delete_snapshot(session: AsyncSession, motorbike_id: str) -> bool:
    """Delete `motorbike_id`'s used-price row, if any; announce when one existed.

    Returns `True` when a row was deleted, `False` when there was none.
    """
    row = await _get_row(session, motorbike_id)
    if row is None:
        return False

    await session.delete(row)
    await session.commit()
    await _announce(session, motorbike_id)
    return True


async def _get_row(session: AsyncSession, motorbike_id: str) -> MotorbikeUsedPrice | None:
    result = await session.execute(
        select(MotorbikeUsedPrice).where(MotorbikeUsedPrice.motorbike_id == motorbike_id)
    )
    return result.scalar_one_or_none()


def _to_snapshot(row: MotorbikeUsedPrice) -> UsedPriceSnapshot:
    return UsedPriceSnapshot(
        motorbike_id=row.motorbike_id,
        price_min_eur=row.price_min_eur,
        price_max_eur=row.price_max_eur,
        price_median_eur=row.price_median_eur,
        sample_count=row.sample_count,
        as_of=row.as_of,
        sources=list(row.sources),
        is_stale=is_stale(row.as_of),
    )


async def _announce(session: AsyncSession, motorbike_id: str) -> None:
    """Publish the pinned `product.updated` payload — ids only, after commit."""
    await operation_service.notify(session, {"event": "product.updated", "productId": motorbike_id})
