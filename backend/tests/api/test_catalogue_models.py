"""Behavioural tests for the read-only `catalogue-models` JSON:API resource.

Setup follows `test_chats.py`: the in-memory `FakeAsyncSession` stands behind
`get_db_session`, so authentication, the brand lookup, the document list and the
image list really run against seeded rows. The two **join** statements
(`browse_motorbikes`, `get_verified_specs`) are beyond what that fake can
interpret — their SQL is proven by the compiled-SQL tests of step 4.3 — so they
are replaced here by recording fakes. That is deliberate: what these tests are
about is the *wire* (which filters reach the service, which attributes come back,
which ids answer 404), not the SQL.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.schemas.catalogue_models import CatalogueModelSpecs
from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.db.models.source_document import SourceDocument, SourceType
from app.db.models.user import UserRole
from app.db.session import get_db_session
from app.services import catalogue_search_service
from app.services.catalogue_search_service import (
    COMPARISON_SPEC_FIELDS,
    SUMMARY_SPEC_FIELDS,
    BrowseRow,
    BrowseSort,
    VerifiedSpecs,
)
from app.services.naming_service import NameParts
from tests.services.conftest import FakeAsyncSession

PASSWORD = "secret123"

SUMMARY_ATTRIBUTES = {
    "name",
    "manufacturer",
    "category",
    "engineCc",
    "powerKw",
    "wetWeightKg",
    "seatHeightMm",
    "a2Eligible",
    "priceBand",
    "msrpEur",
    "imageUrl",
}
DETAIL_ATTRIBUTES = {
    "name",
    "manufacturer",
    "specs",
    "article",
    "sources",
    "images",
    "variants",
}
SPEC_KEYS = {
    "category",
    "engineCc",
    "cylinders",
    "powerKw",
    "torqueNm",
    "wetWeightKg",
    "seatHeightMm",
    "tankCapacityL",
    "topSpeedKmh",
    "abs",
    "a2Eligible",
    "priceBand",
    "msrpEur",
}


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


def _sign_in(
    api: FastAPI, fake_session: FakeAsyncSession, *, role: UserRole
) -> Iterator[TestClient]:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as client:
        registered = client.post("/auth/register", json={"username": "rider", "password": PASSWORD})
        assert registered.status_code == 201, registered.text
        assert (
            client.post(
                "/auth/login",
                json={"username": "rider", "password": PASSWORD, "rememberMe": False},
            ).status_code
            == 200
        )
        fake_session.users[registered.json()["id"]].role = role
        yield client
    api.dependency_overrides.clear()


@pytest.fixture
def customer(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    """A plain account — the surface this resource is built for."""
    yield from _sign_in(api, fake_session, role=UserRole.USER)


@pytest.fixture
def admin(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    yield from _sign_in(api, fake_session, role=UserRole.ADMIN)


class RecordedBrowse:
    """A stand-in for `browse_motorbikes`: records its keywords, answers a page."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.rows: list[BrowseRow] = []
        self.total = 0

    def answers(self, rows: list[BrowseRow], total: int | None = None) -> None:
        self.rows = rows
        self.total = len(rows) if total is None else total

    async def __call__(self, session: object, **kwargs: Any) -> tuple[list[BrowseRow], int]:
        self.calls.append(kwargs)
        return self.rows, self.total


@pytest.fixture
def browse(monkeypatch: pytest.MonkeyPatch) -> RecordedBrowse:
    """Replace the join statement of `browse_motorbikes` with a recorder."""
    recorded = RecordedBrowse()
    monkeypatch.setattr(catalogue_search_service, "browse_motorbikes", recorded)
    return recorded


@pytest.fixture
def verified_specs(monkeypatch: pytest.MonkeyPatch) -> Callable[[VerifiedSpecs | None], None]:
    """Return a setter for what `get_verified_specs` answers on the detail route."""
    answer: list[VerifiedSpecs] = []

    async def record(session: object, motorbike_ids: list[str]) -> list[VerifiedSpecs]:
        return answer

    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", record)

    def configure(specs: VerifiedSpecs | None) -> None:
        answer.clear()
        if specs is not None:
            answer.append(specs)

    return configure


def _parts(motorbike_id: str, name: str) -> NameParts:
    """`NameParts` with no structured identity: `render_name` falls back to
    `query_name` verbatim — these tests are not about naming.
    """
    return NameParts(
        motorbike_id=motorbike_id,
        manufacturer=None,
        buildingline=None,
        model_name=None,
        year_from=None,
        year_to=None,
        query_name=name,
    )


def _summary_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = dict.fromkeys(SUMMARY_SPEC_FIELDS)
    values.update(overrides)
    return values


def _comparison_values(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = dict.fromkeys(COMPARISON_SPEC_FIELDS)
    values.update(overrides)
    return values


def _seed_motorbike(
    session: FakeAsyncSession,
    *,
    name: str = "Honda CB500F",
    status: MotorbikeStatus = MotorbikeStatus.APPROVED,
    manufacturer_id: str | None = None,
) -> Motorbike:
    motorbike = Motorbike(
        query_name=name,
        slug=name.lower().replace(" ", "-"),
        status=status,
        manufacturer_id=manufacturer_id,
    )
    session.add(motorbike)
    return motorbike


def _seed_manufacturer(session: FakeAsyncSession, name: str) -> Manufacturer:
    manufacturer = Manufacturer(name=name, slug=name.lower())
    session.add(manufacturer)
    return manufacturer


# --- GET /api/catalogue-models ------------------------------------------------


def test_list_returns_the_pinned_slim_attributes(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    browse: RecordedBrowse,
) -> None:
    honda = _seed_manufacturer(fake_session, "Honda")
    browse.answers(
        [
            BrowseRow(
                motorbike_id="01ABCMODEL0000000000000001",
                name="Honda CB500F",
                manufacturer_id=honda.id,
                values=_summary_values(category="naked", engine_cc=471, msrp_eur=6800),
                parts=_parts("01ABCMODEL0000000000000001", "Honda CB500F"),
            )
        ],
        total=3,
    )
    fake_session.add(
        MotorbikeImage(
            id="01ABCIMAGE0000000000000001",
            motorbike_id="01ABCMODEL0000000000000001",
            source_url="https://example.test/cb500f.jpg",
            attribution="CC BY-SA",
            status=ImageStatus.APPROVED,
            original_path="images/cb500f.jpg",
        )
    )

    response = customer.get("/api/catalogue-models")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"] == {"totalCount": 3}
    resource = body["data"][0]
    assert resource["type"] == "catalogue-models"
    assert resource["id"] == "01ABCMODEL0000000000000001"
    assert set(resource["attributes"]) == SUMMARY_ATTRIBUTES
    assert resource["attributes"]["manufacturer"] == "Honda"
    assert resource["attributes"]["category"] == "naked"
    assert resource["attributes"]["engineCc"] == 471
    assert resource["attributes"]["msrpEur"] == 6800
    assert resource["attributes"]["imageUrl"] == (
        "/media/motorbikes/01ABCMODEL0000000000000001/01ABCIMAGE0000000000000001_card.webp"
    )


def test_list_without_an_approved_image_has_no_image_url(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    browse.answers(
        [
            BrowseRow(
                motorbike_id="01ABCMODEL0000000000000002",
                name="Suzuki GSR 600",
                manufacturer_id=None,
                values=_summary_values(),
                parts=_parts("01ABCMODEL0000000000000002", "Suzuki GSR 600"),
            )
        ]
    )

    response = customer.get("/api/catalogue-models")

    assert response.status_code == 200, response.text
    attributes = response.json()["data"][0]["attributes"]
    assert attributes["imageUrl"] is None
    assert attributes["manufacturer"] is None
    assert attributes["category"] is None


def test_list_passes_every_filter_family_to_the_service(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    response = customer.get(
        "/api/catalogue-models",
        params={
            "filter[category]": "naked,adventure",
            "filter[priceBand]": "mid",
            "filter[manufacturer]": "01ABCBRAND000000000000001,01ABCBRAND000000000000002",
            "filter[engineCcMin]": 400,
            "filter[engineCcMax]": 900,
            "filter[powerKwMin]": 20,
            "filter[powerKwMax]": 70.5,
            "filter[wetWeightKgMax]": 220,
            "filter[seatHeightMmMax]": 800,
            "filter[a2Eligible]": "true",
            "page[number]": 2,
            "page[size]": 10,
        },
    )

    assert response.status_code == 200, response.text
    assert len(browse.calls) == 1
    call = browse.calls[0]
    assert call["filters"].values() == {
        "categories": ["naked", "adventure"],
        "engine_cc_min": 400,
        "engine_cc_max": 900,
        "power_kw_min": 20.0,
        "power_kw_max": 70.5,
        "wet_weight_kg_max": 220.0,
        "seat_height_mm_max": 800,
        "a2_eligible": True,
        "price_bands": ["mid"],
    }
    assert call["manufacturer_ids"] == [
        "01ABCBRAND000000000000001",
        "01ABCBRAND000000000000002",
    ]
    assert call["limit"] == 10
    assert call["offset"] == 10


def test_list_without_filters_states_nothing(customer: TestClient, browse: RecordedBrowse) -> None:
    assert customer.get("/api/catalogue-models").status_code == 200
    call = browse.calls[0]
    assert call["filters"].is_empty()
    assert call["manufacturer_ids"] is None
    assert call["sort"] is BrowseSort.NAME


@pytest.mark.parametrize(
    ("parameter", "value"),
    [("filter[category]", "naked,spaceship"), ("filter[priceBand]", "free")],
)
def test_list_unknown_vocabulary_member_returns_400_invalid_filter(
    customer: TestClient, browse: RecordedBrowse, parameter: str, value: str
) -> None:
    response = customer.get("/api/catalogue-models", params={parameter: value})

    assert response.status_code == 400
    errors = response.json()["errors"]
    assert len(errors) == 1
    assert errors[0]["code"] == "invalid-filter"


def test_list_unknown_manufacturer_id_is_not_an_error(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    """An id that matches nothing answers an empty page, never a 400."""
    response = customer.get(
        "/api/catalogue-models", params={"filter[manufacturer]": "01NOSUCHBRAND00000000000"}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"data": [], "meta": {"totalCount": 0}}
    assert browse.calls[0]["manufacturer_ids"] == ["01NOSUCHBRAND00000000000"]


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("filter[engineCcMin]", "roughly 500"),
        ("filter[powerKwMax]", "lots"),
        ("filter[seatHeightMmMax]", "low"),
        ("filter[a2Eligible]", "maybe"),
        ("sort", "cheapest"),
        ("page[size]", "101"),
    ],
)
def test_list_junk_typed_parameters_return_422(
    customer: TestClient, browse: RecordedBrowse, parameter: str, value: str
) -> None:
    response = customer.get("/api/catalogue-models", params={parameter: value})

    assert response.status_code == 422


# --- filter[...] caps (5.5) -----------------------------------------------------


def test_list_filter_with_the_maximum_member_count_is_accepted(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    members = ",".join(f"m{i}" for i in range(50))

    response = customer.get("/api/catalogue-models", params={"filter[manufacturer]": members})

    assert response.status_code == 200, response.text
    assert len(browse.calls[0]["manufacturer_ids"]) == 50


def test_list_filter_beyond_the_maximum_member_count_returns_400_invalid_filter(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    members = ",".join(f"m{i}" for i in range(51))

    response = customer.get("/api/catalogue-models", params={"filter[manufacturer]": members})

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "invalid-filter"


def test_list_filter_member_at_the_maximum_length_is_accepted(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    response = customer.get("/api/catalogue-models", params={"filter[manufacturer]": "m" * 128})

    assert response.status_code == 200, response.text


def test_list_filter_member_beyond_the_maximum_length_returns_400_invalid_filter(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    response = customer.get("/api/catalogue-models", params={"filter[manufacturer]": "m" * 129})

    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "invalid-filter"


# --- catalogue numeric filter plausibility bounds (5.5) -------------------------


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("filter[engineCcMin]", 25),
        ("filter[engineCcMax]", 3000),
        ("filter[powerKwMin]", 0.5),
        ("filter[powerKwMax]", 400),
        ("filter[wetWeightKgMax]", 600),
        ("filter[seatHeightMmMax]", 1200),
    ],
)
def test_list_numeric_filter_at_the_plausibility_boundary_is_accepted(
    customer: TestClient, browse: RecordedBrowse, parameter: str, value: float
) -> None:
    response = customer.get("/api/catalogue-models", params={parameter: value})

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("filter[engineCcMin]", 24),
        ("filter[engineCcMax]", 3001),
        ("filter[powerKwMin]", 0.4),
        ("filter[powerKwMax]", 400.1),
        ("filter[wetWeightKgMax]", 600.1),
        ("filter[seatHeightMmMax]", 1201),
    ],
)
def test_list_numeric_filter_beyond_the_plausibility_boundary_returns_422(
    customer: TestClient, browse: RecordedBrowse, parameter: str, value: float
) -> None:
    response = customer.get("/api/catalogue-models", params={parameter: value})

    assert response.status_code == 422


# --- page[number] upper bound (5.5) ---------------------------------------------


def test_list_page_number_at_the_ceiling_is_accepted(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    response = customer.get("/api/catalogue-models", params={"page[number]": 10_000})

    assert response.status_code == 200, response.text


def test_list_page_number_beyond_the_ceiling_returns_422(
    customer: TestClient, browse: RecordedBrowse
) -> None:
    response = customer.get("/api/catalogue-models", params={"page[number]": 10_001})

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("wire", "expected"),
    [
        ("name", BrowseSort.NAME),
        ("-name", BrowseSort.NAME_DESC),
        ("msrpEur", BrowseSort.MSRP_EUR),
        ("-msrpEur", BrowseSort.MSRP_EUR_DESC),
    ],
)
def test_list_sort_reaches_the_service_verbatim(
    customer: TestClient, browse: RecordedBrowse, wire: str, expected: BrowseSort
) -> None:
    assert customer.get("/api/catalogue-models", params={"sort": wire}).status_code == 200
    assert browse.calls[0]["sort"] is expected


def test_list_requires_a_session(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as anonymous:
        response = anonymous.get("/api/catalogue-models")
    api.dependency_overrides.clear()

    assert response.status_code == 401


def test_list_is_open_to_admins_too(admin: TestClient, browse: RecordedBrowse) -> None:
    """`current_user`, not `current_admin`: an admin is a user."""
    assert admin.get("/api/catalogue-models").status_code == 200


# --- GET /api/catalogue-models/{id} -------------------------------------------


def test_detail_returns_specs_article_sources_and_images(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    verified_specs: Callable[[VerifiedSpecs | None], None],
) -> None:
    honda = _seed_manufacturer(fake_session, "Honda")
    motorbike = _seed_motorbike(fake_session, manufacturer_id=honda.id)
    verified_specs(
        VerifiedSpecs(
            motorbike_id=motorbike.id,
            name=motorbike.query_name,
            values=_comparison_values(category="naked", engine_cc=471, a2_eligible=True),
            parts=_parts(motorbike.id, motorbike.query_name),
        )
    )
    fake_session.add(
        SourceDocument(
            motorbike_id=motorbike.id,
            source_type=SourceType.WIKIPEDIA,
            source_url="https://en.wikipedia.org/wiki/Honda_CB500F",
            source_title="Honda CB500F",
            raw_path="raw/wiki.html",
            content_markdown="# Honda CB500F\n\nA middleweight naked.",
            fetched_at=datetime.now(UTC),
        )
    )
    fake_session.add(
        SourceDocument(
            motorbike_id=motorbike.id,
            source_type=SourceType.PRODUCT,
            source_url="https://honda.test/cb500f",
            source_title="Honda — CB500F",
            raw_path="raw/honda.html",
            content_markdown="Marketing prose that is never served here.",
            fetched_at=datetime.now(UTC),
        )
    )
    fake_session.add(
        MotorbikeImage(
            id="01ABCIMAGE0000000000000009",
            motorbike_id=motorbike.id,
            source_url="https://example.test/cb500f.jpg",
            attribution="Photo: Someone, CC BY-SA 4.0",
            status=ImageStatus.APPROVED,
            original_path="images/cb500f.jpg",
        )
    )
    fake_session.add(
        MotorbikeImage(
            motorbike_id=motorbike.id,
            source_url="https://example.test/pending.jpg",
            attribution=None,
            status=ImageStatus.PENDING,
            original_path="images/pending.jpg",
        )
    )

    response = customer.get(f"/api/catalogue-models/{motorbike.id}")

    assert response.status_code == 200, response.text
    resource = response.json()["data"]
    assert resource["type"] == "catalogue-models"
    assert resource["id"] == motorbike.id
    attributes = resource["attributes"]
    assert set(attributes) == DETAIL_ATTRIBUTES
    assert attributes["name"] == "Honda CB500F"
    assert attributes["manufacturer"] == "Honda"

    assert set(attributes["specs"]) == SPEC_KEYS
    assert attributes["specs"]["engineCc"] == 471
    assert attributes["specs"]["a2Eligible"] is True
    assert attributes["specs"]["torqueNm"] is None

    assert attributes["article"] == "# Honda CB500F\n\nA middleweight naked."
    # Wikipedia first, and never the prose of the other documents.
    assert attributes["sources"] == [
        {
            "sourceTitle": "Honda CB500F",
            "sourceUrl": "https://en.wikipedia.org/wiki/Honda_CB500F",
        },
        {"sourceTitle": "Honda — CB500F", "sourceUrl": "https://honda.test/cb500f"},
    ]

    # Approved only, with the pinned variant URLs and the attribution.
    assert attributes["images"] == [
        {
            "thumb": f"/media/motorbikes/{motorbike.id}/01ABCIMAGE0000000000000009_thumb.webp",
            "card": f"/media/motorbikes/{motorbike.id}/01ABCIMAGE0000000000000009_card.webp",
            "detail": f"/media/motorbikes/{motorbike.id}/01ABCIMAGE0000000000000009_detail.webp",
            "attribution": "Photo: Someone, CC BY-SA 4.0",
        }
    ]


def test_detail_sources_never_include_a_listing_document(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    verified_specs: Callable[[VerifiedSpecs | None], None],
) -> None:
    """D12, fourth carve-out: a classifieds link is not provenance for a spec."""
    motorbike = _seed_motorbike(fake_session)
    verified_specs(
        VerifiedSpecs(
            motorbike_id=motorbike.id,
            name=motorbike.query_name,
            values=_comparison_values(),
            parts=_parts(motorbike.id, motorbike.query_name),
        )
    )
    fake_session.add(
        SourceDocument(
            motorbike_id=motorbike.id,
            source_type=SourceType.WIKIPEDIA,
            source_url="https://en.wikipedia.org/wiki/Suzuki_GSR600",
            source_title="Suzuki GSR600",
            raw_path="raw/wiki.html",
            content_markdown="# Suzuki GSR600\n\nA naked bike.",
            fetched_at=datetime.now(UTC),
        )
    )
    fake_session.add(
        SourceDocument(
            motorbike_id=motorbike.id,
            source_type=SourceType.LISTING,
            source_url="https://example.test/classifieds/gsr600",
            source_title="Used GSR600 for sale",
            raw_path="raw/listing.html",
            content_markdown="Asking 4200 EUR, low mileage.",
            fetched_at=datetime.now(UTC),
        )
    )

    response = customer.get(f"/api/catalogue-models/{motorbike.id}")

    assert response.status_code == 200, response.text
    attributes = response.json()["data"]["attributes"]
    assert attributes["sources"] == [
        {
            "sourceTitle": "Suzuki GSR600",
            "sourceUrl": "https://en.wikipedia.org/wiki/Suzuki_GSR600",
        }
    ]


def test_detail_variants_are_projected_from_the_row(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    verified_specs: Callable[[VerifiedSpecs | None], None],
) -> None:
    """Detail only (D6, ui-spec API-2) — the list test below asserts the opposite."""
    motorbike = _seed_motorbike(fake_session)
    motorbike.variants = [
        {
            "slug": "adventure-sports",
            "name": "Adventure Sports",
            "description": "Larger tank, crash bars.",
            "specs": {"tank_capacity_l": 24.8},
        }
    ]
    verified_specs(
        VerifiedSpecs(
            motorbike_id=motorbike.id,
            name=motorbike.query_name,
            values=_comparison_values(),
            parts=_parts(motorbike.id, motorbike.query_name),
        )
    )

    response = customer.get(f"/api/catalogue-models/{motorbike.id}")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["attributes"]["variants"] == [
        {
            "slug": "adventure-sports",
            "name": "Adventure Sports",
            "description": "Larger tank, crash bars.",
            "specs": {"tank_capacity_l": 24.8},
        }
    ]


def test_detail_without_stored_variants_is_an_empty_list(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    verified_specs: Callable[[VerifiedSpecs | None], None],
) -> None:
    """`motorbike.variants` is `None` in this test double (never in real Postgres)."""
    motorbike = _seed_motorbike(fake_session)
    verified_specs(
        VerifiedSpecs(
            motorbike_id=motorbike.id,
            name=motorbike.query_name,
            values=_comparison_values(),
            parts=_parts(motorbike.id, motorbike.query_name),
        )
    )

    response = customer.get(f"/api/catalogue-models/{motorbike.id}")

    assert response.json()["data"]["attributes"]["variants"] == []


def test_detail_without_a_wikipedia_document_has_no_article(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    verified_specs: Callable[[VerifiedSpecs | None], None],
) -> None:
    motorbike = _seed_motorbike(fake_session)
    verified_specs(None)
    fake_session.add(
        SourceDocument(
            motorbike_id=motorbike.id,
            source_type=SourceType.UPLOAD,
            source_url=None,
            source_title="Uploaded brochure",
            raw_path="raw/brochure.pdf",
            content_markdown="Brochure text.",
            fetched_at=datetime.now(UTC),
        )
    )

    response = customer.get(f"/api/catalogue-models/{motorbike.id}")

    assert response.status_code == 200, response.text
    attributes = response.json()["data"]["attributes"]
    assert attributes["article"] is None
    # A URL-less upload keeps its title and answers a null URL.
    assert attributes["sources"] == [{"sourceTitle": "Uploaded brochure", "sourceUrl": None}]
    assert attributes["images"] == []
    # No verified revision at all still renders a full table of gaps.
    assert set(attributes["specs"]) == SPEC_KEYS
    assert set(attributes["specs"].values()) == {None}


@pytest.mark.parametrize(
    "status",
    [
        MotorbikeStatus.BACKLOG,
        MotorbikeStatus.INGESTING,
        MotorbikeStatus.IN_REVIEW,
        MotorbikeStatus.REJECTED,
    ],
)
def test_detail_of_a_non_approved_model_returns_404_not_found(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    verified_specs: Callable[[VerifiedSpecs | None], None],
    status: MotorbikeStatus,
) -> None:
    verified_specs(None)
    motorbike = _seed_motorbike(fake_session, status=status)

    response = customer.get(f"/api/catalogue-models/{motorbike.id}")

    assert response.status_code == 404
    errors = response.json()["errors"]
    assert errors[0]["code"] == "not-found"
    # No existence leak: the same sentence an unknown id produces.
    assert errors[0]["detail"] == f"No catalogue model with id '{motorbike.id}'."


def test_detail_of_an_unknown_id_returns_404_not_found(
    customer: TestClient, verified_specs: Callable[[VerifiedSpecs | None], None]
) -> None:
    verified_specs(None)

    response = customer.get("/api/catalogue-models/" + "0" * 26)

    assert response.status_code == 404
    assert response.json()["errors"][0]["code"] == "not-found"


def test_detail_requires_a_session(api: FastAPI, fake_session: FakeAsyncSession) -> None:
    motorbike = _seed_motorbike(fake_session)
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as anonymous:
        response = anonymous.get(f"/api/catalogue-models/{motorbike.id}")
    api.dependency_overrides.clear()

    assert response.status_code == 401


# --- No write routes ----------------------------------------------------------


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_writes_are_not_routed(customer: TestClient, method: str) -> None:
    collection = customer.request(method, "/api/catalogue-models")
    detail = customer.request(method, "/api/catalogue-models/" + "0" * 26)

    assert collection.status_code == 405
    assert detail.status_code == 405


# --- D6: the claim is never catalogue data -------------------------------------


def test_suggestion_and_type_codes_never_appear_on_catalogue_models(
    customer: TestClient,
    fake_session: FakeAsyncSession,
    browse: RecordedBrowse,
    verified_specs: Callable[[VerifiedSpecs | None], None],
) -> None:
    """A row carrying a real claim still answers neither key, list or detail."""
    motorbike = _seed_motorbike(fake_session)
    motorbike.suggestion = {
        "source": "bike-list.txt",
        "raw": "Honda CB500F",
        "manufacturer": "Honda",
        "model": "CB500F",
        "year_from": None,
        "year_to": None,
        "in_production": True,
        "year_ranges": [],
        "type_codes": ["PC64"],
        "links": [],
    }
    motorbike.type_codes = ["PC64"]
    browse.answers(
        [
            BrowseRow(
                motorbike_id=motorbike.id,
                name=motorbike.query_name,
                manufacturer_id=None,
                values=_summary_values(),
                parts=_parts(motorbike.id, motorbike.query_name),
            )
        ]
    )
    verified_specs(
        VerifiedSpecs(
            motorbike_id=motorbike.id,
            name=motorbike.query_name,
            values=_comparison_values(),
            parts=_parts(motorbike.id, motorbike.query_name),
        )
    )

    list_attributes = customer.get("/api/catalogue-models").json()["data"][0]["attributes"]
    detail_attributes = customer.get(f"/api/catalogue-models/{motorbike.id}").json()["data"][
        "attributes"
    ]

    assert "suggestion" not in list_attributes
    assert "typeCodes" not in list_attributes
    assert "suggestion" not in detail_attributes
    assert "typeCodes" not in detail_attributes


# --- Drift guards -------------------------------------------------------------


def test_spec_attributes_match_the_frozen_comparison_fields() -> None:
    """The detail specification is exactly the 13 frozen fields, in their order."""
    assert tuple(CatalogueModelSpecs.model_fields) == COMPARISON_SPEC_FIELDS
