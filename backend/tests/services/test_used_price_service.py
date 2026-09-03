"""`app/services/used_price_service.py` — snapshot writes, reads, staleness.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from app.db.models.motorbike import Motorbike
from app.db.models.motorbike_used_price import MotorbikeUsedPrice
from app.services import used_price_service
from tests.services.conftest import FakeAsyncSession

AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
SOURCES = [
    {
        "source_document_id": "01SOURCEDOCUMENTEXAMPLE01",
        "url": "https://example.com/listing",
        "title": "Example listing page",
        "sample_count": 3,
        "prices": [4200, 4500, 4800],
    }
]


def _motorbike(session: FakeAsyncSession) -> Motorbike:
    motorbike = Motorbike(query_name="Suzuki GSR 600", slug="suzuki-gsr-600")
    session.add(motorbike)
    return motorbike


def test_get_snapshot_returns_none_when_no_row(fake_session: FakeAsyncSession) -> None:
    motorbike = _motorbike(fake_session)

    result = asyncio.run(used_price_service.get_snapshot(fake_session, motorbike.id))

    assert result is None


def test_upsert_snapshot_inserts_a_new_row(fake_session: FakeAsyncSession) -> None:
    motorbike = _motorbike(fake_session)

    row = asyncio.run(
        used_price_service.upsert_snapshot(
            fake_session,
            motorbike.id,
            price_min_eur=4000,
            price_max_eur=5000,
            price_median_eur=4500,
            sample_count=3,
            as_of=AS_OF,
            sources=SOURCES,
        )
    )

    assert isinstance(row, MotorbikeUsedPrice)
    assert row.motorbike_id == motorbike.id
    assert row.price_min_eur == 4000
    assert row.price_max_eur == 5000
    assert row.price_median_eur == 4500
    assert row.sample_count == 3
    assert row.as_of == AS_OF
    assert row.sources == SOURCES
    assert len(fake_session.rows(MotorbikeUsedPrice)) == 1


def test_upsert_snapshot_replaces_the_existing_row(fake_session: FakeAsyncSession) -> None:
    motorbike = _motorbike(fake_session)
    asyncio.run(
        used_price_service.upsert_snapshot(
            fake_session,
            motorbike.id,
            price_min_eur=4000,
            price_max_eur=5000,
            price_median_eur=4500,
            sample_count=3,
            as_of=AS_OF,
            sources=SOURCES,
        )
    )

    later = AS_OF + timedelta(days=30)
    row = asyncio.run(
        used_price_service.upsert_snapshot(
            fake_session,
            motorbike.id,
            price_min_eur=4100,
            price_max_eur=5200,
            price_median_eur=4600,
            sample_count=None,
            as_of=later,
            sources=[],
        )
    )

    # Full-object replace, one row per bike (D9) — no second row appeared.
    assert len(fake_session.rows(MotorbikeUsedPrice)) == 1
    assert row.price_min_eur == 4100
    assert row.price_max_eur == 5200
    assert row.price_median_eur == 4600
    assert row.sample_count is None
    assert row.as_of == later
    assert row.sources == []


def test_upsert_snapshot_sample_count_none_round_trips_as_none(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _motorbike(fake_session)

    row = asyncio.run(
        used_price_service.upsert_snapshot(
            fake_session,
            motorbike.id,
            price_min_eur=4000,
            price_max_eur=5000,
            price_median_eur=4500,
            sample_count=None,
            as_of=AS_OF,
            sources=[],
        )
    )

    assert row.sample_count is None
    snapshot = asyncio.run(used_price_service.get_snapshot(fake_session, motorbike.id))
    assert snapshot is not None
    assert snapshot.sample_count is None


def test_upsert_snapshot_announces_product_updated(fake_session: FakeAsyncSession) -> None:
    motorbike = _motorbike(fake_session)
    commits_before = fake_session.commit_count

    asyncio.run(
        used_price_service.upsert_snapshot(
            fake_session,
            motorbike.id,
            price_min_eur=4000,
            price_max_eur=5000,
            price_median_eur=4500,
            sample_count=3,
            as_of=AS_OF,
            sources=SOURCES,
        )
    )

    # The write commits first, then the announcement commits its own
    # `pg_notify` — two commits, in that order, and the notification carries
    # the motorbike id.
    assert fake_session.commit_count == commits_before + 2
    assert [channel for channel, _ in fake_session.notifications] == ["app_events"]
    assert motorbike.id in fake_session.notifications[0][1]


def test_delete_snapshot_returns_false_when_none_existed(fake_session: FakeAsyncSession) -> None:
    motorbike = _motorbike(fake_session)

    deleted = asyncio.run(used_price_service.delete_snapshot(fake_session, motorbike.id))

    assert deleted is False
    assert fake_session.notifications == []


def test_delete_snapshot_removes_the_row_and_announces(fake_session: FakeAsyncSession) -> None:
    motorbike = _motorbike(fake_session)
    asyncio.run(
        used_price_service.upsert_snapshot(
            fake_session,
            motorbike.id,
            price_min_eur=4000,
            price_max_eur=5000,
            price_median_eur=4500,
            sample_count=3,
            as_of=AS_OF,
            sources=SOURCES,
        )
    )
    fake_session.notifications.clear()

    deleted = asyncio.run(used_price_service.delete_snapshot(fake_session, motorbike.id))

    assert deleted is True
    assert fake_session.rows(MotorbikeUsedPrice) == []
    assert [channel for channel, _ in fake_session.notifications] == ["app_events"]
    assert motorbike.id in fake_session.notifications[0][1]

    again = asyncio.run(used_price_service.get_snapshot(fake_session, motorbike.id))
    assert again is None


def test_is_stale_exactly_max_age_is_not_stale() -> None:
    now = AS_OF + timedelta(days=180)

    assert used_price_service.is_stale(AS_OF, now=now) is False


def test_is_stale_one_day_past_max_age_is_stale() -> None:
    now = AS_OF + timedelta(days=181)

    assert used_price_service.is_stale(AS_OF, now=now) is True


def test_get_snapshot_reflects_is_stale(fake_session: FakeAsyncSession) -> None:
    motorbike = _motorbike(fake_session)
    asyncio.run(
        used_price_service.upsert_snapshot(
            fake_session,
            motorbike.id,
            price_min_eur=4000,
            price_max_eur=5000,
            price_median_eur=4500,
            sample_count=3,
            as_of=datetime.now(UTC) - timedelta(days=181),
            sources=SOURCES,
        )
    )

    snapshot = asyncio.run(used_price_service.get_snapshot(fake_session, motorbike.id))

    assert snapshot is not None
    assert snapshot.is_stale is True
