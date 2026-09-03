"""Tests for `app.services.image_service`.

The fixture images are generated with Pillow rather than committed, so the source
dimensions the width caps are asserted against are visible in the test itself.
Downloads are answered by an `httpx2.MockTransport`: no network, no waiting.

The first test is the important one — the variant paths on disk and the variant
URLs the API computes are two independent implementations of one pinned formula.
"""

import asyncio
import io
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx2
import pytest
from PIL import Image

from app.api.schemas import images as image_schemas
from app.core.config import get_settings
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.services import image_service
from app.services.ingestion import fetch
from tests.services.conftest import FakeAsyncSession

Handler = Callable[[httpx2.Request], httpx2.Response]

MOTORBIKE_ID = "01JZZH0K3QZ8V9W4M8F7Q2R5T1"
IMAGE_URL = "https://upload.example.test/gsr600.jpg"


@pytest.fixture
def media_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point MEDIA_DIR at a temporary directory for the duration of one test."""
    directory = tmp_path / "media"
    monkeypatch.setenv("MEDIA_DIR", str(directory))
    get_settings.cache_clear()
    yield directory
    get_settings.cache_clear()


def image_bytes(width: int, height: int, *, image_format: str = "JPEG") -> bytes:
    """Return an encoded image of exactly `width` × `height` pixels."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(128, 0, 0)).save(buffer, format=image_format)
    return buffer.getvalue()


def image_response(payload: bytes, *, content_type: str = "image/jpeg") -> httpx2.Response:
    return httpx2.Response(200, headers={"content-type": content_type}, content=payload)


def run_ingest(
    session: FakeAsyncSession,
    handler: Handler,
    *,
    url: str = IMAGE_URL,
    attribution: str | None = None,
) -> image_service.ImageOutcome:
    """Ingest one image against `handler`, with the politeness delay switched off."""

    async def call() -> image_service.ImageOutcome:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler), follow_redirects=True
        ) as client:
            return await image_service.ingest_image(
                session,
                MOTORBIKE_ID,
                url,
                attribution,
                client=client,
                gate=fetch.PolitenessGate(delay_seconds=0.0),
            )

    return asyncio.run(call())


def test_variant_paths_are_the_paths_of_the_api_variant_urls() -> None:
    image_id = "01JZZH0K3QZ8V9W4M8F7Q2R5T2"

    urls = image_schemas.variant_urls(MOTORBIKE_ID, image_id)

    for variant in image_service.VARIANT_WIDTHS:
        path = image_service.variant_path(MOTORBIKE_ID, image_id, variant)
        assert getattr(urls, variant) == f"{image_schemas.MEDIA_URL_PREFIX}/{path}"


def test_writes_the_three_variants_capped_at_the_pinned_widths(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    outcome = run_ingest(fake_session, lambda request: image_response(image_bytes(1600, 900)))

    assert isinstance(outcome, image_service.ImageResult)
    assert dict(outcome.variant_paths) == {
        variant: image_service.variant_path(MOTORBIKE_ID, outcome.image.id, variant)
        for variant in ("thumb", "card", "detail")
    }
    for variant, expected_size in (
        ("thumb", (320, 180)),
        ("card", (640, 360)),
        ("detail", (1280, 720)),
    ):
        with Image.open(media_dir / outcome.variant_paths[variant]) as written:
            assert (written.format, written.size) == ("WEBP", expected_size)


def test_caps_the_width_instead_of_upscaling_a_small_source(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    outcome = run_ingest(fake_session, lambda request: image_response(image_bytes(200, 100)))

    assert isinstance(outcome, image_service.ImageResult)
    for path in outcome.variant_paths.values():
        with Image.open(media_dir / path) as written:
            assert (written.format, written.size) == ("WEBP", (200, 100))


def test_retains_the_original_bytes_and_creates_the_pending_row(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    payload = image_bytes(800, 600, image_format="PNG")

    outcome = run_ingest(
        fake_session,
        lambda request: image_response(payload, content_type="image/png"),
        attribution="A. Photographer · CC BY-SA 4.0",
    )

    assert isinstance(outcome, image_service.ImageResult)
    image = outcome.image
    assert fake_session.rows(MotorbikeImage) == [image]
    assert fake_session.commit_count == 1
    # No NOTIFY here: document and image creation events belong to step 2.14.
    assert fake_session.notifications == []
    assert (image.motorbike_id, image.status, image.source_url) == (
        MOTORBIKE_ID,
        ImageStatus.PENDING,
        IMAGE_URL,
    )
    assert image.attribution == "A. Photographer · CC BY-SA 4.0"
    assert image.original_path == f"motorbikes/{MOTORBIKE_ID}/{image.id}_original.png"
    assert (media_dir / image.original_path).read_bytes() == payload


def test_records_the_url_that_answered_after_a_redirect(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    final_url = "https://cdn.example.test/gsr600-full.jpg"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == IMAGE_URL:
            return httpx2.Response(302, headers={"location": final_url})
        return image_response(image_bytes(400, 300))

    outcome = run_ingest(fake_session, handler)

    assert isinstance(outcome, image_service.ImageResult)
    assert outcome.image.source_url == final_url


def test_non_image_content_type_is_a_typed_warning(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    outcome = run_ingest(
        fake_session,
        lambda request: httpx2.Response(
            200, headers={"content-type": "text/html; charset=utf-8"}, content=b"<html></html>"
        ),
    )

    assert isinstance(outcome, image_service.ImageFailure)
    assert outcome.reason is image_service.ImageFailureReason.UNSUPPORTED_CONTENT_TYPE
    assert "text/html" in outcome.detail
    assert fake_session.rows(MotorbikeImage) == []
    assert not media_dir.exists()


def test_an_error_status_is_a_typed_warning(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    outcome = run_ingest(fake_session, lambda request: httpx2.Response(404))

    assert isinstance(outcome, image_service.ImageFailure)
    assert outcome.reason is image_service.ImageFailureReason.DOWNLOAD_FAILED
    assert fake_session.rows(MotorbikeImage) == []


def test_undecodable_bytes_are_a_typed_warning(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    outcome = run_ingest(fake_session, lambda request: image_response(b"not an image at all"))

    assert isinstance(outcome, image_service.ImageFailure)
    assert outcome.reason is image_service.ImageFailureReason.UNREADABLE_IMAGE
    assert fake_session.rows(MotorbikeImage) == []


def test_an_unfetchable_url_never_opens_a_connection(fake_session: FakeAsyncSession) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:  # pragma: no cover - never called
        raise AssertionError("the transport must not be reached")

    outcome = run_ingest(fake_session, handler, url="file:///etc/passwd")

    assert isinstance(outcome, image_service.ImageFailure)
    assert outcome.reason is image_service.ImageFailureReason.DOWNLOAD_FAILED
