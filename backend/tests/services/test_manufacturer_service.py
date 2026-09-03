"""`app/services/manufacturer_service.py` — normalisation, get-or-create, reads.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.

The concurrency case needs two things the fake session deliberately does not
have — a failing commit and a `rollback` — so it gets a small local subclass
that simulates the parallel ingestion winning the race for a slug.
"""

import asyncio
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.services import manufacturer_service, product_service
from tests.services.conftest import FakeAsyncSession


class _RacingSession(FakeAsyncSession):
    """Rejects the first commit as a duplicate slug, as PostgreSQL would.

    `insert_winner` is what makes the race real: the row of the transaction that
    committed first appears in the store just before our insert is rejected, so
    the re-select after the rollback has something to find.
    """

    def __init__(self, *, winner: Manufacturer | None) -> None:
        super().__init__()
        self.winner = winner
        self.rollbacks = 0
        self.added: list[Any] = []
        self._fail_next_commit = True

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        super().add(obj)

    async def commit(self) -> None:
        if self._fail_next_commit:
            self._fail_next_commit = False
            if self.winner is not None:
                self.store(Manufacturer)[self.winner.id] = self.winner
            raise IntegrityError("INSERT INTO manufacturers", {}, Exception("duplicate key value"))
        await super().commit()

    async def rollback(self) -> None:
        self.rollbacks += 1
        for obj in self.added:
            self.store(type(obj)).pop(obj.id, None)
        self.added.clear()


def _get_or_create(session: FakeAsyncSession, name: str) -> Manufacturer:
    return asyncio.run(manufacturer_service.get_or_create(session, name))


# --- normalize_name -----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Suzuki", "Suzuki"),
        ("  BMW  ", "BMW"),
        ("Moto\t Guzzi", "Moto Guzzi"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_name_trims_collapses_and_reports_emptiness(
    raw: str | None, expected: str | None
) -> None:
    assert manufacturer_service.normalize_name(raw) == expected


def test_normalize_name_truncates_to_the_column_width() -> None:
    assert len(manufacturer_service.normalize_name("x" * 200) or "") == 64


# --- normalize_name: known-marque mapping (D14, step 6.16) --------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Kawasaki Motors", "Kawasaki"),
        ("KTM Sportmotorcycle", "KTM"),
        ("kawasaki motors", "Kawasaki"),
        ("bmw", "BMW"),
        ("Honda Motor", "Honda"),
        ("Kawasaki", "Kawasaki"),
        ("KAWASAKI", "Kawasaki"),
    ],
)
def test_normalize_name_maps_a_known_marque_prefix_onto_the_canonical_spelling(
    raw: str, expected: str
) -> None:
    assert manufacturer_service.normalize_name(raw) == expected


def test_normalize_name_leaves_an_unknown_marque_verbatim() -> None:
    assert manufacturer_service.normalize_name("MV Agusta") == "MV Agusta"


def test_normalize_name_never_matches_a_marque_mid_string() -> None:
    # The marque must be the first word — "Honda" appearing later in the
    # string must never trigger the mapping.
    assert manufacturer_service.normalize_name("Big Honda Fan Club") == "Big Honda Fan Club"


# --- get_or_create ------------------------------------------------------------


def test_get_or_create_stores_the_display_name_and_the_derived_slug(
    fake_session: FakeAsyncSession,
) -> None:
    manufacturer = _get_or_create(fake_session, "  Moto   Guzzi ")

    assert (manufacturer.name, manufacturer.slug) == ("Moto Guzzi", "moto-guzzi")
    assert fake_session.rows(Manufacturer) == [manufacturer]
    assert fake_session.commit_count == 1


@pytest.mark.parametrize("spelling", ["Suzuki", "suzuki", "  SUZUKI  "])
def test_get_or_create_returns_the_existing_row_for_an_equal_slug(
    fake_session: FakeAsyncSession, spelling: str
) -> None:
    first = _get_or_create(fake_session, "Suzuki")

    again = _get_or_create(fake_session, spelling)

    assert again.id == first.id
    # First-seen casing wins, and nothing was written a second time.
    assert again.name == "Suzuki"
    assert len(fake_session.rows(Manufacturer)) == 1


@pytest.mark.parametrize("name", ["", "   ", "???"])
def test_get_or_create_rejects_a_name_without_an_identity(
    fake_session: FakeAsyncSession, name: str
) -> None:
    with pytest.raises(ValueError):
        _get_or_create(fake_session, name)

    assert fake_session.rows(Manufacturer) == []


def test_get_or_create_takes_the_concurrent_row_after_an_integrity_error() -> None:
    winner = Manufacturer(id="0" * 26, name="Suzuki", slug="suzuki")
    session = _RacingSession(winner=winner)

    manufacturer = _get_or_create(session, "Suzuki")

    assert manufacturer is winner
    assert session.rollbacks == 1
    assert session.rows(Manufacturer) == [winner]


def test_get_or_create_re_raises_when_the_conflict_cannot_be_explained() -> None:
    session = _RacingSession(winner=None)

    with pytest.raises(IntegrityError):
        _get_or_create(session, "Suzuki")


# --- get_by_ids / list_manufacturers ------------------------------------------


def test_get_by_ids_maps_known_ids_and_ignores_the_rest(
    fake_session: FakeAsyncSession,
) -> None:
    suzuki = _get_or_create(fake_session, "Suzuki")
    _get_or_create(fake_session, "Honda")

    found = asyncio.run(manufacturer_service.get_by_ids(fake_session, [suzuki.id, "1" * 26]))

    assert found == {suzuki.id: suzuki}


def test_get_by_ids_without_ids_asks_nothing(fake_session: FakeAsyncSession) -> None:
    assert asyncio.run(manufacturer_service.get_by_ids(fake_session, [])) == {}


def test_list_manufacturers_paginates_by_name_and_reports_the_total(
    fake_session: FakeAsyncSession,
) -> None:
    for name in ("Suzuki", "Honda", "KTM"):
        _get_or_create(fake_session, name)

    rows, total = asyncio.run(
        manufacturer_service.list_manufacturers(fake_session, limit=2, offset=0)
    )

    assert [row.name for row in rows] == ["Honda", "KTM"]
    assert total == 3


# --- product_service.assign_manufacturer --------------------------------------


def test_assign_manufacturer_sets_the_reference_and_announces_the_product(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    manufacturer = _get_or_create(fake_session, "Suzuki")
    fake_session.notifications.clear()

    asyncio.run(product_service.assign_manufacturer(fake_session, motorbike, manufacturer.id))

    assert fake_session.rows(Motorbike)[0].manufacturer_id == manufacturer.id
    assert motorbike.status is MotorbikeStatus.BACKLOG
    assert [channel for channel, _ in fake_session.notifications] == ["app_events"]
    assert motorbike.id in fake_session.notifications[0][1]


def test_assign_manufacturer_clears_the_reference_with_none(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = asyncio.run(product_service.create_backlog(fake_session, "Suzuki GSR 600"))
    manufacturer = _get_or_create(fake_session, "Suzuki")
    asyncio.run(product_service.assign_manufacturer(fake_session, motorbike, manufacturer.id))

    asyncio.run(product_service.assign_manufacturer(fake_session, motorbike, None))

    assert fake_session.rows(Motorbike)[0].manufacturer_id is None
