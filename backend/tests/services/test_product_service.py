"""`app/services/product_service.py` — slugs, the transition matrix, spec writes.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.
"""

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.db.models.motorbike_spec import MotorbikeSpec, SpecKind
from app.services import product_service
from app.services.product_service import (
    LEGAL_TRANSITIONS,
    DuplicateModelError,
    IncompleteIdentityError,
    InvalidTransitionError,
)
from tests.services.conftest import FakeAsyncSession

LEGAL_PAIRS = [
    (current, requested)
    for current, allowed in LEGAL_TRANSITIONS.items()
    for requested in sorted(allowed)
]
ILLEGAL_PAIRS = [
    (current, requested)
    for current in MotorbikeStatus
    for requested in MotorbikeStatus
    if (current, requested) not in LEGAL_PAIRS
]


def _backlog(session: FakeAsyncSession, name: str = "Suzuki GSR 600") -> Motorbike:
    return asyncio.run(product_service.create_backlog(session, name))


def _give_identity(motorbike: Motorbike) -> Motorbike:
    """Fill the three D4-guarded fields directly, bypassing `assign_identity`.

    These tests exercise `transition`'s status workflow, not identity
    assignment (that is `test_assign_identity_*` below), so a plain attribute
    write is enough to satisfy the `approved` guard.
    """
    motorbike.manufacturer_id = "01MANUFACTUREREXAMPLEPLC0"
    motorbike.model_name = "GSR 600"
    motorbike.year_from = 2011
    return motorbike


def _in_status(
    session: FakeAsyncSession,
    status: MotorbikeStatus,
    name: str = "Suzuki GSR 600",
    *,
    with_identity: bool = False,
) -> Motorbike:
    """Return a stored motorbike parked in `status`, bypassing the matrix.

    `with_identity` fills the D4-guarded fields too, for tests that approve
    the row and need the guard to pass.
    """
    motorbike = _backlog(session, name)
    motorbike.status = status
    if with_identity:
        _give_identity(motorbike)
    return motorbike


def _spec_of(session: FakeAsyncSession, motorbike_id: str, kind: SpecKind) -> MotorbikeSpec | None:
    matches = [
        spec
        for spec in session.rows(MotorbikeSpec)
        if spec.motorbike_id == motorbike_id and spec.kind is kind
    ]
    assert len(matches) <= 1, "more than one spec row per (motorbike, kind)"
    return matches[0] if matches else None


def _image(session: FakeAsyncSession, motorbike_id: str, status: ImageStatus) -> MotorbikeImage:
    image = MotorbikeImage(
        motorbike_id=motorbike_id,
        source_url="https://example.invalid/bike.jpg",
        original_path=f"motorbikes/{motorbike_id}/original.jpg",
        status=status,
    )
    session.add(image)
    return image


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Suzuki GSR 600", "suzuki-gsr-600"),
        ("  Suzuki   GSR 600  ", "suzuki-gsr-600"),
        ("BMW R1250GS Adventure", "bmw-r1250gs-adventure"),
        ("Ducati Multistrada V4 (2022)", "ducati-multistrada-v4-2022"),
        ("KTM 390 Duke!!!", "ktm-390-duke"),
    ],
)
def test_slugify_pinned_rule(name: str, expected: str) -> None:
    assert product_service.slugify(name) == expected


def test_create_backlog_stores_slug_and_backlog_status(fake_session: FakeAsyncSession) -> None:
    motorbike = _backlog(fake_session, "  Suzuki GSR 600 ")

    assert motorbike.query_name == "Suzuki GSR 600"
    assert motorbike.slug == "suzuki-gsr-600"
    assert motorbike.status is MotorbikeStatus.BACKLOG
    assert motorbike.id is not None
    # One commit for the row, one for the `product.updated` announcement that
    # follows it (`operation_service.notify` commits its own `pg_notify`).
    assert fake_session.commit_count == 2


def test_create_backlog_duplicate_slug_raises(fake_session: FakeAsyncSession) -> None:
    _backlog(fake_session, "Suzuki GSR 600")

    with pytest.raises(DuplicateModelError):
        _backlog(fake_session, "suzuki gsr-600")


@pytest.mark.parametrize(("current", "requested"), LEGAL_PAIRS)
def test_transition_allows_every_legal_pair(
    fake_session: FakeAsyncSession, current: MotorbikeStatus, requested: MotorbikeStatus
) -> None:
    # `with_identity=True` unconditionally: harmless for every other pair, and
    # required for `in_review -> approved` to clear the D4 guard.
    motorbike = _in_status(fake_session, current, with_identity=True)

    updated = asyncio.run(product_service.transition(fake_session, motorbike, requested))

    assert updated.status is requested


@pytest.mark.parametrize(("current", "requested"), ILLEGAL_PAIRS)
def test_transition_rejects_every_illegal_pair(
    fake_session: FakeAsyncSession, current: MotorbikeStatus, requested: MotorbikeStatus
) -> None:
    motorbike = _in_status(fake_session, current)
    commits_before = fake_session.commit_count

    with pytest.raises(InvalidTransitionError) as raised:
        asyncio.run(product_service.transition(fake_session, motorbike, requested))

    assert raised.value.current is current
    assert raised.value.requested is requested
    assert motorbike.status is current
    assert fake_session.commit_count == commits_before


def test_approval_promotes_draft_and_flips_pending_images_in_one_commit(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW, with_identity=True)
    asyncio.run(
        product_service.upsert_draft_spec(
            fake_session,
            motorbike.id,
            {
                "category": "naked",
                "engine_cc": 599,
                "power_kw": Decimal("58.0"),
                "wet_weight_kg": Decimal("214.0"),
                "extra": {"frame": "aluminium"},
            },
        )
    )
    pending = _image(fake_session, motorbike.id, ImageStatus.PENDING)
    already_rejected = _image(fake_session, motorbike.id, ImageStatus.REJECTED)
    other_bike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW, "Honda CB 500 F")
    other_pending = _image(fake_session, other_bike.id, ImageStatus.PENDING)
    commits_before = fake_session.commit_count

    asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.APPROVED))

    verified = _spec_of(fake_session, motorbike.id, SpecKind.VERIFIED)
    assert verified is not None
    assert verified.category == "naked"
    assert verified.engine_cc == 599
    assert verified.extra == {"frame": "aluminium"}
    # The draft is kept, not moved.
    assert _spec_of(fake_session, motorbike.id, SpecKind.DRAFT) is not None
    assert pending.status is ImageStatus.APPROVED
    assert already_rejected.status is ImageStatus.REJECTED
    assert other_pending.status is ImageStatus.PENDING
    # Status change, promotion and image flip share a single transaction; the
    # second commit is the `product.updated` announcement, which by contract
    # only ever follows a committed change.
    assert fake_session.commit_count == commits_before + 2


def test_approval_without_draft_spec_writes_no_verified_row(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW, with_identity=True)
    pending = _image(fake_session, motorbike.id, ImageStatus.PENDING)

    asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.APPROVED))

    assert _spec_of(fake_session, motorbike.id, SpecKind.VERIFIED) is None
    assert pending.status is ImageStatus.APPROVED


def test_approval_replaces_a_previous_verified_row(fake_session: FakeAsyncSession) -> None:
    motorbike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW, with_identity=True)
    asyncio.run(product_service.upsert_draft_spec(fake_session, motorbike.id, {"engine_cc": 599}))
    asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.APPROVED))
    first = _spec_of(fake_session, motorbike.id, SpecKind.VERIFIED)

    motorbike.status = MotorbikeStatus.IN_REVIEW
    asyncio.run(product_service.upsert_draft_spec(fake_session, motorbike.id, {"engine_cc": 649}))
    asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.APPROVED))

    second = _spec_of(fake_session, motorbike.id, SpecKind.VERIFIED)
    assert second is first
    assert second is not None
    assert second.engine_cc == 649


def test_rejection_retains_draft_spec_and_images(fake_session: FakeAsyncSession) -> None:
    motorbike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW)
    asyncio.run(product_service.upsert_draft_spec(fake_session, motorbike.id, {"engine_cc": 599}))
    pending = _image(fake_session, motorbike.id, ImageStatus.PENDING)

    asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.REJECTED))

    assert motorbike.status is MotorbikeStatus.REJECTED
    assert _spec_of(fake_session, motorbike.id, SpecKind.DRAFT) is not None
    assert _spec_of(fake_session, motorbike.id, SpecKind.VERIFIED) is None
    assert pending.status is ImageStatus.PENDING
    # Not terminal: an admin re-queues a fresh ingestion.
    assert asyncio.run(
        product_service.transition(fake_session, motorbike, MotorbikeStatus.INGESTING)
    )


def test_upsert_draft_spec_creates_then_replaces_full_object(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _backlog(fake_session)
    extracted_at = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

    created = asyncio.run(
        product_service.upsert_draft_spec(
            fake_session,
            motorbike.id,
            {
                "category": "naked",
                "engine_cc": 599,
                "seat_height_mm": 785,
                "abs": True,
                "source_hints": {"engine_cc": "wikipedia"},
                "extracted_at": extracted_at,
            },
        )
    )

    assert created.kind is SpecKind.DRAFT
    assert created.engine_cc == 599
    assert created.extra == {}
    assert created.extracted_at == extracted_at

    replaced = asyncio.run(
        product_service.upsert_draft_spec(fake_session, motorbike.id, {"engine_cc": 649})
    )

    # Same row, and every omitted field is reset — writes are full-object.
    assert replaced is created
    assert replaced.engine_cc == 649
    assert replaced.category is None
    assert replaced.seat_height_mm is None
    assert replaced.abs is None
    assert replaced.source_hints is None
    assert replaced.extracted_at is None
    assert replaced.extra == {}


def test_upsert_draft_spec_rejects_unknown_field(fake_session: FakeAsyncSession) -> None:
    motorbike = _backlog(fake_session)

    with pytest.raises(ValueError, match="horsepower"):
        asyncio.run(
            product_service.upsert_draft_spec(fake_session, motorbike.id, {"horsepower": 80})
        )


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        # Both limits exactly met: 35.0 kW and 35.0/175.0 == 0.2 exactly.
        ({"power_kw": Decimal("35.0"), "wet_weight_kg": Decimal("175.0")}, True),
        # One step over the power limit.
        ({"power_kw": Decimal("35.1"), "wet_weight_kg": Decimal("400.0")}, False),
        # Power within limits, ratio just over 0.2.
        ({"power_kw": Decimal("35.0"), "wet_weight_kg": Decimal("174.9")}, False),
        ({"power_kw": Decimal("25.0"), "wet_weight_kg": Decimal("170.0")}, True),
        # Not derivable: one input unknown.
        ({"power_kw": Decimal("35.0")}, None),
        ({"wet_weight_kg": Decimal("175.0")}, None),
        ({}, None),
        # An explicit value always wins over the formula.
        (
            {"power_kw": Decimal("35.0"), "wet_weight_kg": Decimal("175.0"), "a2_eligible": False},
            False,
        ),
        (
            {"power_kw": Decimal("58.0"), "wet_weight_kg": Decimal("214.0"), "a2_eligible": True},
            True,
        ),
    ],
)
def test_a2_eligible_derivation(
    fake_session: FakeAsyncSession, values: dict[str, Any], expected: bool | None
) -> None:
    motorbike = _backlog(fake_session)

    spec = asyncio.run(product_service.upsert_draft_spec(fake_session, motorbike.id, values))

    assert spec.a2_eligible is expected


# --- step 4.3: the image reads the customer catalogue needs -------------------
#
# `DISTINCT ON` is PostgreSQL syntax the in-memory `FakeAsyncSession` cannot
# interpret, so these follow the compiled-SQL convention from 3.7: a local
# recording session, and the statement itself is what is asserted.

BIKE_ID = "01J0BIKE00000000000000000A"
OTHER_BIKE_ID = "01J0BIKE00000000000000000B"

_PARAMETER = re.compile(r"%\([a-z_0-9]+\)s")


@dataclass(frozen=True, slots=True)
class _Image:
    """The one attribute the mapping is keyed by."""

    motorbike_id: str


class _RecordedScalars:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class _RecordedResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _RecordedScalars:
        return _RecordedScalars(self._rows)


class RecordingSession:
    """Records the statements issued and replays scripted rows. Never commits."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows if rows is not None else []
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _RecordedResult:
        self.statements.append(statement)
        return _RecordedResult(self.rows)


def _compiled(session: RecordingSession, index: int = 0) -> Any:
    return session.statements[index].compile(dialect=postgresql.dialect())


def _sql(session: RecordingSession, index: int = 0) -> str:
    return _PARAMETER.sub("?", str(_compiled(session, index)))


def test_the_newest_approved_image_lookup_is_one_distinct_on_statement() -> None:
    """One round trip for a whole page, and approved is a `WHERE`, not a hope."""
    session = RecordingSession()

    asyncio.run(product_service.newest_approved_images(session, [BIKE_ID, OTHER_BIKE_ID]))
    sql = _sql(session)
    params = _compiled(session).params

    assert len(session.statements) == 1
    assert "SELECT DISTINCT ON (motorbike_images.motorbike_id)" in sql
    assert "motorbike_images.motorbike_id IN (__[POSTCOMPILE_motorbike_id_1])" in sql
    assert "motorbike_images.status = ?" in sql
    assert params["status_1"] is ImageStatus.APPROVED
    # The `DISTINCT ON` expression has to lead the ordering for "newest per
    # model" to be well defined at all.
    assert (
        "ORDER BY motorbike_images.motorbike_id, motorbike_images.created_at DESC, "
        "motorbike_images.id DESC" in sql
    )


def test_the_newest_approved_images_are_keyed_by_motorbike() -> None:
    """One winner per model; a model without an approved image is simply absent."""
    session = RecordingSession([_Image(BIKE_ID)])

    images = asyncio.run(product_service.newest_approved_images(session, [BIKE_ID, OTHER_BIKE_ID]))

    assert set(images) == {BIKE_ID}
    assert images[BIKE_ID].motorbike_id == BIKE_ID


def test_no_ids_means_no_image_round_trip() -> None:
    """An empty page is answered without asking the database."""
    session = RecordingSession()

    assert asyncio.run(product_service.newest_approved_images(session, [])) == {}
    assert session.statements == []


def test_list_images_stays_unfiltered_by_moderation_state_by_default() -> None:
    """The admin review screen must keep seeing pending pictures."""
    session = RecordingSession()

    asyncio.run(product_service.list_images(session, motorbike_id=BIKE_ID))
    sql = _sql(session)

    assert "motorbike_images.status" not in sql.split("WHERE")[1]
    assert "ORDER BY motorbike_images.created_at DESC, motorbike_images.id DESC" in sql


def test_list_images_restricts_to_the_requested_moderation_states() -> None:
    """The customer gallery asks for approved rows in SQL, not after the fact."""
    session = RecordingSession()

    asyncio.run(
        product_service.list_images(session, motorbike_id=BIKE_ID, statuses=[ImageStatus.APPROVED])
    )

    assert "motorbike_images.status IN (__[POSTCOMPILE_status_1])" in _sql(session)
    assert _compiled(session).params["status_1"] == [ImageStatus.APPROVED]


# `normalise_buildingline` / `list_buildinglines` — reads only, no writes.

_MANUFACTURER_ID = "01J0MANUFACTURER00000000AA"
_OTHER_MANUFACTURER_ID = "01J0MANUFACTURER00000000BB"


def test_list_buildinglines_returns_distinct_non_null_values_sorted(
    fake_session: FakeAsyncSession,
) -> None:
    gs = _backlog(fake_session, "BMW R 1250 GS")
    gs.manufacturer_id = _MANUFACTURER_ID
    gs.buildingline = "GS"
    rt = _backlog(fake_session, "BMW R 1250 RT")
    rt.manufacturer_id = _MANUFACTURER_ID
    rt.buildingline = "RT"
    duplicate_family = _backlog(fake_session, "BMW R 1300 GS")
    duplicate_family.manufacturer_id = _MANUFACTURER_ID
    duplicate_family.buildingline = "GS"
    no_family = _backlog(fake_session, "BMW F 900 R")
    no_family.manufacturer_id = _MANUFACTURER_ID
    other_brand = _backlog(fake_session, "Honda Africa Twin")
    other_brand.manufacturer_id = _OTHER_MANUFACTURER_ID
    other_brand.buildingline = "Africa Twin"

    result = asyncio.run(product_service.list_buildinglines(fake_session, _MANUFACTURER_ID))

    assert result == ["GS", "RT"]


def test_list_buildinglines_no_writes(fake_session: FakeAsyncSession) -> None:
    asyncio.run(product_service.list_buildinglines(fake_session, _MANUFACTURER_ID))

    assert fake_session.commit_count == 0


def test_normalise_buildingline_trims_and_collapses_inner_whitespace(
    fake_session: FakeAsyncSession,
) -> None:
    result = asyncio.run(
        product_service.normalise_buildingline(fake_session, _MANUFACTURER_ID, "  GS   Adventure  ")
    )

    assert result == "GS Adventure"


def test_normalise_buildingline_empty_or_none_is_none(fake_session: FakeAsyncSession) -> None:
    assert (
        asyncio.run(product_service.normalise_buildingline(fake_session, _MANUFACTURER_ID, "   "))
        is None
    )
    assert (
        asyncio.run(product_service.normalise_buildingline(fake_session, _MANUFACTURER_ID, None))
        is None
    )


def test_normalise_buildingline_reuses_the_stored_casing(fake_session: FakeAsyncSession) -> None:
    gs = _backlog(fake_session, "BMW R 1250 GS")
    gs.manufacturer_id = _MANUFACTURER_ID
    gs.buildingline = "GS"

    result = asyncio.run(
        product_service.normalise_buildingline(fake_session, _MANUFACTURER_ID, "gs")
    )

    assert result == "GS"


def test_normalise_buildingline_first_writer_spelling_is_never_overwritten(
    fake_session: FakeAsyncSession,
) -> None:
    # The match is case-insensitive, not whitespace-insensitive: "GS" and
    # "G S" are different family names, so only a same-shaped later spelling
    # joins the first writer's casing.
    gs = _backlog(fake_session, "BMW R 1250 GS Adventure")
    gs.manufacturer_id = _MANUFACTURER_ID
    gs.buildingline = "GS Adventure"

    result = asyncio.run(
        product_service.normalise_buildingline(fake_session, _MANUFACTURER_ID, "gs   ADVENTURE")
    )

    assert result == "GS Adventure"


def test_normalise_buildingline_new_spelling_stands_when_no_match_exists(
    fake_session: FakeAsyncSession,
) -> None:
    result = asyncio.run(
        product_service.normalise_buildingline(fake_session, _MANUFACTURER_ID, "GS")
    )

    assert result == "GS"


def test_normalise_buildingline_no_writes(fake_session: FakeAsyncSession) -> None:
    asyncio.run(product_service.normalise_buildingline(fake_session, _MANUFACTURER_ID, "GS"))

    assert fake_session.commit_count == 0


# --- `assign_identity` (step 6.12) ---------------------------------------------


def _manufacturer(session: FakeAsyncSession, name: str = "BMW", slug: str = "bmw") -> Manufacturer:
    manufacturer = Manufacturer(name=name, slug=slug)
    session.add(manufacturer)
    return manufacturer


def test_assign_identity_full_replace_and_canonical_slug(fake_session: FakeAsyncSession) -> None:
    motorbike = _backlog(fake_session, "BMW R 1250 GS import")
    manufacturer = _manufacturer(fake_session)

    updated = asyncio.run(
        product_service.assign_identity(
            fake_session,
            motorbike,
            manufacturer_id=manufacturer.id,
            buildingline="GS",
            model_name="R 1250 GS",
            year_from=2019,
            year_to=2023,
            type_codes=["k50"],
            variants=[],
        )
    )

    assert updated.manufacturer_id == manufacturer.id
    assert updated.buildingline == "GS"
    assert updated.model_name == "R 1250 GS"
    assert updated.year_from == 2019
    assert updated.year_to == 2023
    assert updated.type_codes == ["K50"]
    assert updated.variants == []
    assert updated.slug == "bmw/r-1250-gs/2019-2023"


def test_assign_identity_open_ended_year_range_slug(fake_session: FakeAsyncSession) -> None:
    motorbike = _backlog(fake_session, "Yamaha MT-07 import")
    manufacturer = _manufacturer(fake_session, "Yamaha", "yamaha")

    updated = asyncio.run(
        product_service.assign_identity(
            fake_session,
            motorbike,
            manufacturer_id=manufacturer.id,
            buildingline=None,
            model_name="MT-07",
            year_from=2025,
            year_to=None,
            type_codes=[],
            variants=[],
        )
    )

    assert updated.slug == "yamaha/mt-07/2025-"


def test_assign_identity_incomplete_leaves_the_existing_slug_untouched(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _backlog(fake_session, "BMW R 1250 GS import")
    provisional_slug = motorbike.slug
    manufacturer = _manufacturer(fake_session)

    updated = asyncio.run(
        product_service.assign_identity(
            fake_session,
            motorbike,
            manufacturer_id=manufacturer.id,
            buildingline="GS",
            model_name=None,  # missing model_name keeps the identity incomplete
            year_from=None,
            year_to=None,
            type_codes=[],
            variants=[],
        )
    )

    assert updated.slug == provisional_slug
    assert updated.manufacturer_id == manufacturer.id
    assert updated.model_name is None


def test_assign_identity_unknown_manufacturer_id_raises_value_error(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _backlog(fake_session, "BMW R 1250 GS import")

    with pytest.raises(ValueError, match="ghost-manufacturer"):
        asyncio.run(
            product_service.assign_identity(
                fake_session,
                motorbike,
                manufacturer_id="ghost-manufacturer",
                buildingline=None,
                model_name="R 1250 GS",
                year_from=2019,
                year_to=2023,
                type_codes=[],
                variants=[],
            )
        )


def test_assign_identity_collision_raises_before_writing_anything(
    fake_session: FakeAsyncSession,
) -> None:
    manufacturer = _manufacturer(fake_session)
    asyncio.run(
        product_service.assign_identity(
            fake_session,
            _backlog(fake_session, "BMW R 1250 GS import 1"),
            manufacturer_id=manufacturer.id,
            buildingline=None,
            model_name="R 1250 GS",
            year_from=2019,
            year_to=2023,
            type_codes=[],
            variants=[],
        )
    )
    motorbike = _backlog(fake_session, "BMW R 1250 GS import 2")
    original_slug = motorbike.slug
    commits_before = fake_session.commit_count

    with pytest.raises(DuplicateModelError):
        asyncio.run(
            product_service.assign_identity(
                fake_session,
                motorbike,
                manufacturer_id=manufacturer.id,
                buildingline=None,
                model_name="R 1250 GS",
                year_from=2019,
                year_to=2023,
                type_codes=[],
                variants=[],
            )
        )

    assert motorbike.slug == original_slug
    assert motorbike.model_name is None
    assert fake_session.commit_count == commits_before


def test_assign_identity_announces_product_updated(fake_session: FakeAsyncSession) -> None:
    motorbike = _backlog(fake_session, "BMW R 1250 GS import")
    manufacturer = _manufacturer(fake_session)
    fake_session.notifications.clear()

    asyncio.run(
        product_service.assign_identity(
            fake_session,
            motorbike,
            manufacturer_id=manufacturer.id,
            buildingline=None,
            model_name="R 1250 GS",
            year_from=2019,
            year_to=2023,
            type_codes=[],
            variants=[],
        )
    )

    assert [channel for channel, _ in fake_session.notifications] == ["app_events"]


def test_assign_identity_logs_dropped_type_codes(
    fake_session: FakeAsyncSession, caplog: pytest.LogCaptureFixture
) -> None:
    motorbike = _backlog(fake_session, "BMW R 1250 GS import")
    manufacturer = _manufacturer(fake_session)

    with caplog.at_level("WARNING", logger="app.services.product_service"):
        updated = asyncio.run(
            product_service.assign_identity(
                fake_session,
                motorbike,
                manufacturer_id=manufacturer.id,
                buildingline=None,
                model_name="R 1250 GS",
                year_from=2019,
                year_to=2023,
                type_codes=["not a valid code!!"],
                variants=[],
            )
        )

    assert updated.type_codes == []
    assert any("Dropped type code" in message for message in caplog.messages)


# --- The `approved` guard (D4, step 6.12) --------------------------------------


@pytest.mark.parametrize(
    ("missing_field",),
    [("manufacturer_id",), ("model_name",), ("year_from",)],
)
def test_transition_to_approved_raises_per_missing_field(
    fake_session: FakeAsyncSession, missing_field: str
) -> None:
    motorbike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW, with_identity=True)
    setattr(motorbike, missing_field, None)
    commits_before = fake_session.commit_count

    with pytest.raises(IncompleteIdentityError) as raised:
        asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.APPROVED))

    assert raised.value.missing_fields == [missing_field]
    assert missing_field in str(raised.value)
    assert motorbike.status is MotorbikeStatus.IN_REVIEW
    assert fake_session.commit_count == commits_before


def test_transition_to_approved_raises_with_every_field_missing(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW)

    with pytest.raises(IncompleteIdentityError) as raised:
        asyncio.run(product_service.transition(fake_session, motorbike, MotorbikeStatus.APPROVED))

    assert raised.value.missing_fields == ["manufacturer_id", "model_name", "year_from"]


def test_transition_to_approved_succeeds_when_identity_is_complete(
    fake_session: FakeAsyncSession,
) -> None:
    motorbike = _in_status(fake_session, MotorbikeStatus.IN_REVIEW, with_identity=True)

    updated = asyncio.run(
        product_service.transition(fake_session, motorbike, MotorbikeStatus.APPROVED)
    )

    assert updated.status is MotorbikeStatus.APPROVED
