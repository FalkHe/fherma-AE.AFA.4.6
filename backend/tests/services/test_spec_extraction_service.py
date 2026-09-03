"""Tests for the spec-extraction service (step 2.17).

The LLM is always a stub (`extraction.extract_spec` is replaced), so what is
under test is the service's own jobs: which documents go into the prompt and how
much of them, that the result lands in the **draft** row and nowhere else, that
the extracted brand becomes a `manufacturers` row the entry points at (step
2b.2), and that every expected failure comes back as a typed warning instead of
an exception the ingestion job would have to survive.
"""

import asyncio
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from app.core.config import get_settings
from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike
from app.db.models.motorbike_spec import SPEC_FIELDS, MotorbikeSpec, SpecKind
from app.db.models.source_document import SourceDocument, SourceType
from app.llm import extraction
from app.llm.models import MissingApiKeyError
from app.services import (
    document_service,
    manufacturer_service,
    product_service,
    spec_extraction_service,
)
from tests.services.conftest import FakeAsyncSession

MODEL_NAME = "Suzuki GSR 600"

# What the stubbed model answers with, unless a test says otherwise.
ANSWER = extraction.ExtractedSpec.model_validate(
    {
        "category": "naked",
        "engine_cc": "599 cc",
        "power_kw": "98 hp",
        "wet_weight_kg": "200 kg",
        "source_hints": {"engine_cc": "Wikipedia infobox"},
    }
)


@pytest.fixture
def settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Return a setter for settings the service reads at call time."""

    def override(**environment: object) -> None:
        for key, value in environment.items():
            monkeypatch.setenv(key, str(value))
        get_settings.cache_clear()

    yield override
    get_settings.cache_clear()


@pytest.fixture
def motorbike(fake_session: FakeAsyncSession) -> Motorbike:
    """A catalogue entry, as the job or the CLI finds it."""
    return asyncio.run(product_service.create_backlog(fake_session, MODEL_NAME))


@pytest.fixture
def stub_model(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[Any]]:
    """Replace the LLM call; return the recorder of what it was asked."""

    def install(
        answer: extraction.ExtractedSpec | None = None, error: Exception | None = None
    ) -> list[Any]:
        calls: list[Any] = []

        async def extract_spec(name: str, documents: Any, *, model: str | None = None) -> Any:
            calls.append((name, tuple(documents), model))
            if error is not None:
                raise error
            return answer if answer is not None else ANSWER

        monkeypatch.setattr(extraction, "extract_spec", extract_spec)
        return calls

    return install


def _answer(**values: Any) -> extraction.ExtractedSpec:
    """One stubbed model answer, built the way the parser would build it."""
    return extraction.ExtractedSpec.model_validate(values)


def _document(
    source_type: SourceType, title: str, markdown: str, url: str | None = None
) -> SourceDocument:
    return SourceDocument(
        source_type=source_type,
        source_title=title,
        source_url=url,
        raw_path="sources/x/y.html",
        content_markdown=markdown,
    )


def _store_document(
    session: FakeAsyncSession,
    motorbike: Motorbike,
    source_type: SourceType,
    markdown: str,
    title: str = "Title",
) -> SourceDocument:
    return asyncio.run(
        document_service.create_document(
            session,
            motorbike.id,
            source_type=source_type,
            source_title=title,
            raw_path=f"sources/{motorbike.id}/{title}.html",
            content_markdown=markdown,
            fetched_at=motorbike.created_at,
        )
    )


def _drafts(session: FakeAsyncSession) -> list[MotorbikeSpec]:
    return [spec for spec in session.rows(MotorbikeSpec) if spec.kind is SpecKind.DRAFT]


# --- input assembly -----------------------------------------------------------


def test_the_wikipedia_document_goes_first() -> None:
    """Pinned order: the article is the most reliable single description."""
    documents = [
        _document(SourceType.MAGAZINE, "Review", "review"),
        _document(SourceType.WIKIPEDIA, "Suzuki GSR600", "article"),
        _document(SourceType.PRODUCT, "Suzuki", "product"),
    ]

    assembled = spec_extraction_service.assemble_documents(documents)

    assert [document.title for document in assembled] == ["Suzuki GSR600", "Review", "Suzuki"]


def test_every_document_is_head_truncated() -> None:
    """Specifications live at the top; a long review must not crowd them out."""
    documents = [_document(SourceType.WIKIPEDIA, "Long", "x" * 40_000)]

    assembled = spec_extraction_service.assemble_documents(documents)

    assert len(assembled[0].markdown) == spec_extraction_service.DOCUMENT_MAX_CHARS


def test_the_total_input_is_capped_and_the_rest_dropped() -> None:
    """The budget is spent front to back — Wikipedia first, remainder cut off."""
    documents = [
        _document(SourceType.WIKIPEDIA, "Article", "a" * 8_000),
        _document(SourceType.PRODUCT, "Product", "b" * 8_000),
        _document(SourceType.MAGAZINE, "Review", "c" * 8_000),
    ]

    assembled = spec_extraction_service.assemble_documents(documents, max_input_chars=10_000)

    assert [(document.title, len(document.markdown)) for document in assembled] == [
        ("Article", 8_000),
        ("Product", 2_000),
    ]


def test_the_default_budget_comes_from_configuration(
    settings_override: Callable[..., None],
) -> None:
    settings_override(EXTRACTION_MAX_INPUT_CHARS=5_000)
    documents = [_document(SourceType.WIKIPEDIA, "Article", "a" * 8_000)]

    assembled = spec_extraction_service.assemble_documents(documents)

    assert len(assembled[0].markdown) == 5_000


def test_a_document_without_text_is_left_out() -> None:
    documents = [
        _document(SourceType.WIKIPEDIA, "Article", "   \n  "),
        _document(SourceType.PRODUCT, "Product", "599 cc"),
    ]

    assembled = spec_extraction_service.assemble_documents(documents)

    assert [document.title for document in assembled] == ["Product"]


def test_a_listing_document_never_reaches_the_extraction_prompt() -> None:
    """D12, third carve-out: a used ad is not a specification source."""
    documents = [
        _document(SourceType.WIKIPEDIA, "Suzuki GSR600", "article"),
        _document(SourceType.LISTING, "Used GSR600 for sale", "Asking 4200 EUR."),
    ]

    assembled = spec_extraction_service.assemble_documents(documents)

    assert [document.title for document in assembled] == ["Suzuki GSR600"]
    assert not any("4200" in document.markdown for document in assembled)


def test_the_documents_carry_their_provenance_into_the_prompt() -> None:
    documents = [
        _document(SourceType.WIKIPEDIA, "Suzuki GSR600", "article", "https://en.wikipedia.org/x")
    ]

    assembled = spec_extraction_service.assemble_documents(documents)

    assert assembled[0].source_type == "wikipedia"
    assert assembled[0].url == "https://en.wikipedia.org/x"


# --- the write ----------------------------------------------------------------


def test_extraction_writes_the_draft_specification(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    calls = stub_model()
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert calls[0][0] == MODEL_NAME
    draft = outcome.spec
    assert draft.kind is SpecKind.DRAFT
    assert (draft.category, draft.engine_cc) == ("naked", 599)
    assert draft.power_kw == 73.1
    assert draft.source_hints == {"engine_cc": "Wikipedia infobox"}
    # The service stamps the extraction time; the model never does.
    assert draft.extracted_at is not None
    # ...and the spec write derived A2 eligibility from power and weight (2.1).
    assert draft.a2_eligible is False


def test_running_twice_leaves_one_draft_and_never_touches_verified(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    """Re-running replaces the draft: the pinned full-object upsert semantics."""
    stub_model()
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")
    verified = MotorbikeSpec(
        motorbike_id=motorbike.id, kind=SpecKind.VERIFIED, engine_cc=650, extra={}
    )
    fake_session.add(verified)

    first = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))
    second = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(first, spec_extraction_service.ExtractionResult)
    assert isinstance(second, spec_extraction_service.ExtractionResult)
    assert len(_drafts(fake_session)) == 1
    assert second.spec.id == first.spec.id
    assert verified.engine_cc == 650


def test_the_write_is_the_full_frozen_column_set(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    """Full-object replace: a field the model did not fill is reset, not kept."""
    stub_model()
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")
    asyncio.run(
        product_service.upsert_draft_spec(fake_session, motorbike.id, {"seat_height_mm": 785})
    )

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert list(outcome.values) == list(SPEC_FIELDS)
    assert outcome.spec.seat_height_mm is None


# --- the manufacturer ---------------------------------------------------------


def test_the_extracted_brand_becomes_a_manufacturer_row_and_the_reference(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    """The brand is no spec column: it gets its own row, after the draft write."""
    stub_model(answer=_answer(manufacturer="  Suzuki ", engine_cc="599 cc"))
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    manufacturer = fake_session.rows(Manufacturer)[0]
    assert (manufacturer.name, manufacturer.slug) == ("Suzuki", "suzuki")
    assert motorbike.manufacturer_id == manufacturer.id
    # The brand never reaches the frozen column set.
    assert "manufacturer" not in outcome.values


def test_a_second_model_of_a_known_brand_reuses_its_row(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    stub_model(answer=_answer(manufacturer="Suzuki"))
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")
    other = asyncio.run(product_service.create_backlog(fake_session, "Suzuki SV 650"))
    _store_document(fake_session, other, SourceType.WIKIPEDIA, "645 cc", title="Other")

    asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))
    asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, other))

    assert len(fake_session.rows(Manufacturer)) == 1
    assert motorbike.manufacturer_id == other.manufacturer_id is not None


@pytest.mark.parametrize("brand", [None, "", "   "])
def test_no_brand_leaves_the_reference_untouched(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
    brand: str | None,
) -> None:
    stub_model(answer=_answer(manufacturer=brand))
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert fake_session.rows(Manufacturer) == []
    assert motorbike.manufacturer_id is None


# --- typed failures -----------------------------------------------------------


def test_a_model_without_documents_is_skipped_with_a_warning(
    fake_session: FakeAsyncSession, motorbike: Motorbike, stub_model: Callable[..., list[Any]]
) -> None:
    calls = stub_model()

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionFailure)
    assert outcome.reason is spec_extraction_service.ExtractionFailureReason.NO_DOCUMENTS
    assert outcome.detail == spec_extraction_service.MISSING_DOCUMENTS_DETAIL
    # No prompt was rendered and no draft row was written.
    assert calls == []
    assert _drafts(fake_session) == []


def test_a_missing_api_key_is_a_typed_failure_not_an_exception(
    fake_session: FakeAsyncSession, motorbike: Motorbike, stub_model: Callable[..., list[Any]]
) -> None:
    """Deterministic configuration problem: reported, never retried, never fatal."""
    stub_model(error=MissingApiKeyError())
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionFailure)
    assert outcome.reason is spec_extraction_service.ExtractionFailureReason.MISSING_API_KEY
    assert outcome.detail == spec_extraction_service.MISSING_KEY_DETAIL
    assert _drafts(fake_session) == []


def test_any_gateway_or_parser_error_is_a_typed_failure(
    fake_session: FakeAsyncSession, motorbike: Motorbike, stub_model: Callable[..., list[Any]]
) -> None:
    stub_model(error=RuntimeError("OpenRouter answered 502"))
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionFailure)
    assert outcome.reason is spec_extraction_service.ExtractionFailureReason.MODEL_ERROR
    assert "RuntimeError" in outcome.detail
    assert "OpenRouter answered 502" in outcome.detail
    assert _drafts(fake_session) == []


def test_a_bad_manufacturer_never_costs_the_run_its_specification(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same policy as the rest of the service: the draft stands, the brand is not."""
    stub_model(answer=_answer(manufacturer="Suzuki", engine_cc="599 cc"))
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")

    async def _explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("manufacturers table is on fire")

    monkeypatch.setattr(manufacturer_service, "get_or_create", _explode)

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert outcome.spec.engine_cc == 599
    assert fake_session.rows(Manufacturer) == []
    assert motorbike.manufacturer_id is None


def test_a_manufacturer_without_an_identity_is_skipped(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    """`get_or_create` rejects "???"; that is a skip, not a failed extraction."""
    stub_model(answer=_answer(manufacturer="???"))
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "a bike")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert fake_session.rows(Manufacturer) == []
    assert motorbike.manufacturer_id is None


def test_an_empty_extraction_still_records_the_attempt(
    fake_session: FakeAsyncSession, motorbike: Motorbike, stub_model: Callable[..., list[Any]]
) -> None:
    """All-null is a legitimate answer: the draft row records that it ran."""
    stub_model(answer=extraction.ExtractedSpec())
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "a bike")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert outcome.spec.engine_cc is None
    assert outcome.spec.extracted_at is not None
    assert outcome.spec.extra == {}


# --- identity (step 6.15) -------------------------------------------------------

IDENTITY_ANSWER = extraction.ExtractedSpec.model_validate(
    {
        "manufacturer": "BMW",
        "model_name": "R 1250 GS",
        "buildingline": "GS",
        "year_from": 2019,
        "year_to": 2023,
        "type_codes": ["K50"],
        "variants": [{"name": "Adventure", "specs": {"tank_capacity_l": 30}}],
    }
)


def test_identity_is_assigned_from_a_full_extraction(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    stub_model(answer=IDENTITY_ANSWER)
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "R 1250 GS")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert outcome.identity_warnings == ()
    assert motorbike.model_name == "R 1250 GS"
    assert motorbike.buildingline == "GS"
    assert (motorbike.year_from, motorbike.year_to) == (2019, 2023)
    assert motorbike.type_codes == ["K50"]
    assert [variant["name"] for variant in motorbike.variants] == ["Adventure"]
    manufacturer = fake_session.rows(Manufacturer)[0]
    assert manufacturer.name == "BMW"
    assert motorbike.manufacturer_id == manufacturer.id
    assert motorbike.slug == "bmw/r-1250-gs/2019-2023"


def test_model_name_none_assigns_the_manufacturer_only(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full-object `assign_identity` replace with nulls must not wipe an identity."""
    calls: list[Any] = []

    async def _spy(*args: Any, **kwargs: Any) -> Motorbike:
        calls.append((args, kwargs))
        return motorbike

    monkeypatch.setattr(product_service, "assign_identity", _spy)
    stub_model(answer=_answer(manufacturer="Suzuki", engine_cc="599 cc"))
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "599 cc")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert calls == []
    assert outcome.identity_warnings == ()
    manufacturer = fake_session.rows(Manufacturer)[0]
    assert manufacturer.name == "Suzuki"
    assert motorbike.manufacturer_id == manufacturer.id
    assert motorbike.model_name is None


def test_extraction_merge_prefers_the_existing_non_null_identity(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    """D2b: a stored non-NULL value wins, type codes union, empty variants only."""
    honda = asyncio.run(manufacturer_service.get_or_create(fake_session, "Honda"))
    asyncio.run(
        product_service.assign_identity(
            fake_session,
            motorbike,
            manufacturer_id=honda.id,
            buildingline="Adventure",
            model_name="R 1300 GS",
            year_from=2023,
            year_to=None,
            type_codes=["K81"],
            variants=[{"name": "Trophy", "description": "Rally kit"}],
        )
    )
    stub_model(answer=IDENTITY_ANSWER)  # manufacturer BMW, model_name R 1250 GS, ...
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "R 1250 GS")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    # Existing non-NULL values win over the (differing) extracted ones.
    assert motorbike.manufacturer_id == honda.id
    assert motorbike.buildingline == "Adventure"
    assert motorbike.model_name == "R 1300 GS"
    assert motorbike.year_from == 2023
    # Existing NULL is filled from the extraction.
    assert motorbike.year_to == 2023
    # type_codes: union of stored and extracted.
    assert motorbike.type_codes == ["K50", "K81"]
    # variants: the non-empty stored list is kept, the extracted one discarded.
    assert [variant["name"] for variant in motorbike.variants] == ["Trophy"]


def test_extraction_fills_null_identity_fields_but_keeps_an_existing_manufacturer(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    """A partially-corrected row (manufacturer only) still gets the rest filled."""
    honda = asyncio.run(manufacturer_service.get_or_create(fake_session, "Honda"))
    asyncio.run(product_service.assign_manufacturer(fake_session, motorbike, honda.id))
    stub_model(answer=IDENTITY_ANSWER)  # extracted manufacturer is BMW, ignored below
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "R 1250 GS")

    asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert motorbike.manufacturer_id == honda.id
    assert motorbike.model_name == "R 1250 GS"
    assert motorbike.year_from == 2019


def test_a_raising_assign_identity_does_not_fail_the_extraction(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`DuplicateModelError` included — the draft specification always stands."""

    async def _explode(*args: Any, **kwargs: Any) -> Motorbike:
        raise product_service.DuplicateModelError("bmw/r-1250-gs/2019-2023")

    monkeypatch.setattr(product_service, "assign_identity", _explode)
    stub_model(answer=IDENTITY_ANSWER)
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "R 1250 GS")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert outcome.spec.extracted_at is not None
    assert motorbike.model_name is None
    assert outcome.identity_warnings == ()


def test_identity_warnings_carry_the_normalisers_dropped_entries(
    fake_session: FakeAsyncSession,
    motorbike: Motorbike,
    stub_model: Callable[..., list[Any]],
) -> None:
    stub_model(
        answer=_answer(
            model_name="R 1250 GS",
            year_from=2019,
            type_codes=["not a valid code!!", "K50"],
            variants=[{"name": "Adventure", "specs": {"bogus_key": 1}}],
        )
    )
    _store_document(fake_session, motorbike, SourceType.WIKIPEDIA, "R 1250 GS")

    outcome = asyncio.run(spec_extraction_service.extract_draft_spec(fake_session, motorbike))

    assert isinstance(outcome, spec_extraction_service.ExtractionResult)
    assert len(outcome.identity_warnings) == 2
    assert motorbike.type_codes == ["K50"]
    assert motorbike.variants[0]["specs"] == {}
