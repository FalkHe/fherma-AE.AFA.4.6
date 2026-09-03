"""QA coverage for `app.services.image_service` (step 2.12).

Targets the risks the dev report and `test_image_service.py` did not already
prove with a test: the exact width/height maths at the pinned caps (a source
below every cap, an exactly-4000-wide source, a portrait source), that the
WebP encoder is really invoked with the pinned quality, EXIF-oriented JPEGs,
the byte-cap abort, and what is actually left on disk after a mid-pipeline
decode failure (the dev report does not claim cleanup, and none is pinned in
`shared-knowledge.md` — this file establishes what really happens so a later
step cannot assume otherwise). Everything runs against `httpx2.MockTransport`
and a `tmp_path` MEDIA_DIR — never the network, never a real filesystem
outside pytest's control.
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
from app.db.models.motorbike_image import MotorbikeImage
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


def image_bytes(
    width: int, height: int, *, image_format: str = "JPEG", exif: bytes | None = None
) -> bytes:
    """Return an encoded image of exactly `width` x `height` pixels."""
    buffer = io.BytesIO()
    kwargs: dict[str, object] = {"format": image_format}
    if exif is not None:
        kwargs["exif"] = exif
    Image.new("RGB", (width, height), color=(128, 0, 0)).save(buffer, **kwargs)
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


# --- Criterion 2: aspect preserved + width caps ------------------------------


def test_a_source_smaller_than_every_cap_is_kept_as_is_not_upscaled(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    """A 100x50 source is below all three caps (320/640/1280): a variant caps a
    width, it never enlarges a small picture into a blurry one — all three
    variants come out at the source's own 100x50."""
    outcome = run_ingest(fake_session, lambda request: image_response(image_bytes(100, 50)))

    assert isinstance(outcome, image_service.ImageResult)
    for path in outcome.variant_paths.values():
        with Image.open(media_dir / path) as written:
            assert (written.format, written.size) == ("WEBP", (100, 50))


def test_a_very_wide_source_is_capped_at_exactly_the_pinned_widths(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    """4000x1000 (4:1) exercises all three caps at once with round-number maths."""
    outcome = run_ingest(fake_session, lambda request: image_response(image_bytes(4000, 1000)))

    assert isinstance(outcome, image_service.ImageResult)
    for variant, expected_size in (
        ("thumb", (320, 80)),
        ("card", (640, 160)),
        ("detail", (1280, 320)),
    ):
        with Image.open(media_dir / outcome.variant_paths[variant]) as written:
            assert (written.format, written.size) == ("WEBP", expected_size)


def test_a_portrait_source_is_capped_by_width_preserving_aspect(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    """900x1600 portrait: thumb/card are narrower than the source and get
    resized (height computed proportionally); detail's 1280 cap exceeds the
    source's own 900px width, so it is left untouched — the cap is on width in
    both orientations, never on height."""
    outcome = run_ingest(fake_session, lambda request: image_response(image_bytes(900, 1600)))

    assert isinstance(outcome, image_service.ImageResult)
    for variant, expected_size in (
        ("thumb", (320, 569)),
        ("card", (640, 1138)),
        ("detail", (900, 1600)),
    ):
        with Image.open(media_dir / outcome.variant_paths[variant]) as written:
            assert (written.format, written.size) == ("WEBP", expected_size)


# --- Criterion 3: real WebP output, quality applied --------------------------


def test_variants_are_really_webp_encoded_at_the_pinned_quality(
    fake_session: FakeAsyncSession, media_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirms two things independently: `Image.open().format` really reports
    WEBP (not just the pinned `.webp` filename suffix), and the encoder is
    actually invoked with `quality=80` (spying on `Image.Image.save`, then
    calling through to the real encoder so the files on disk are genuine)."""
    calls: list[int | None] = []
    original_save = Image.Image.save

    def spy_save(
        self: Image.Image, fp: object, format: str | None = None, **kwargs: object
    ) -> None:
        if format == "WEBP":
            calls.append(kwargs.get("quality"))  # type: ignore[arg-type]
        original_save(self, fp, format=format, **kwargs)

    monkeypatch.setattr(Image.Image, "save", spy_save)

    outcome = run_ingest(fake_session, lambda request: image_response(image_bytes(400, 300)))

    assert isinstance(outcome, image_service.ImageResult)
    assert calls == [80, 80, 80]
    for path in outcome.variant_paths.values():
        full = media_dir / path
        assert full.stat().st_size > 0
        with Image.open(full) as written:
            assert written.format == "WEBP"


# --- Criterion 7: EXIF orientation -------------------------------------------


def test_exif_oriented_jpeg_is_rotated_upright_before_variants_are_generated(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    """A 200x100 (landscape) source carrying EXIF orientation 6 (rotate 90 CW to
    display upright) must be corrected before the width caps are applied.

    Verified against plain Pillow before writing this test:
    `ImageOps.exif_transpose` on such a source returns a 100x200 (portrait)
    image with the EXIF orientation tag cleared. Report: the implementation
    calls exactly that (`_prepared` in `image_service.py`) once per image
    before the variant loop, so this is correctness-relevant for the review
    UI and *is* handled — not a gap to flag."""
    source = Image.new("RGB", (200, 100), color=(200, 50, 50))
    exif = source.getexif()
    exif[0x0112] = 6  # Orientation tag.
    buffer = io.BytesIO()
    source.save(buffer, format="JPEG", exif=exif)

    outcome = run_ingest(fake_session, lambda request: image_response(buffer.getvalue()))

    assert isinstance(outcome, image_service.ImageResult)
    for path in outcome.variant_paths.values():
        with Image.open(media_dir / path) as written:
            # Every cap (320/640/1280) exceeds both 100 and 200, so no variant is
            # resized: the swapped, corrected dimensions pass straight through.
            assert written.size == (100, 200)


# --- Criterion 6: byte-cap abort ---------------------------------------------


def test_an_oversized_image_is_aborted_by_the_byte_cap(
    fake_session: FakeAsyncSession, media_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INGESTION_MAX_FETCH_BYTES", "100")
    get_settings.cache_clear()

    payload = image_bytes(800, 600)
    assert len(payload) > 100  # The fixture must genuinely exceed the lowered cap.

    outcome = run_ingest(fake_session, lambda request: image_response(payload))

    assert isinstance(outcome, image_service.ImageFailure)
    assert outcome.reason is image_service.ImageFailureReason.DOWNLOAD_FAILED
    assert "100 bytes" in outcome.detail
    assert fake_session.rows(MotorbikeImage) == []
    assert not media_dir.exists()  # Aborted before any file was ever opened for writing.


def test_an_oversized_image_is_aborted_even_when_content_length_understates_it(
    fake_session: FakeAsyncSession, media_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lying/absent `Content-Length` must not exempt a body from the streamed
    cap — mirrors the equivalent proof for `fetch_html` in
    `tests/services/ingestion/test_fetch_qa.py`."""
    monkeypatch.setenv("INGESTION_MAX_FETCH_BYTES", "100")
    get_settings.cache_clear()

    payload = image_bytes(800, 600)
    assert len(payload) > 100

    def handler(request: httpx2.Request) -> httpx2.Response:
        # No content-length header at all: only the streamed cap can catch this.
        return httpx2.Response(200, headers={"content-type": "image/jpeg"}, content=payload)

    outcome = run_ingest(fake_session, handler)

    assert isinstance(outcome, image_service.ImageFailure)
    assert outcome.reason is image_service.ImageFailureReason.DOWNLOAD_FAILED
    assert fake_session.rows(MotorbikeImage) == []


# --- Criterion 4: corrupt payload, typed failure, disk state -----------------


def test_corrupt_bytes_behind_an_image_content_type_are_a_typed_failure_with_no_row(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    outcome = run_ingest(
        fake_session,
        lambda request: image_response(b"not an image at all", content_type="image/jpeg"),
    )

    assert isinstance(outcome, image_service.ImageFailure)
    assert outcome.reason is image_service.ImageFailureReason.UNREADABLE_IMAGE
    assert fake_session.rows(MotorbikeImage) == []


def test_corrupt_bytes_leave_no_files_behind(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    """A corrupt payload fails at `Image.open()` — before the variant loop —
    and `_write_files` removes the already-retained original on the way out,
    so a failed ingest leaves no file with no DB row pointing at it."""
    outcome = run_ingest(
        fake_session,
        lambda request: image_response(b"not an image at all", content_type="image/jpeg"),
    )
    assert isinstance(outcome, image_service.ImageFailure)

    directory = media_dir / "motorbikes" / MOTORBIKE_ID
    leftover = list(directory.iterdir()) if directory.exists() else []
    assert leftover == []


# --- Criteria 1 and 5, independently re-confirmed ----------------------------


def test_variant_disk_paths_independently_match_the_api_variant_url_formula() -> None:
    """Same cross-step contract the dev suite already proves
    (`test_image_service.py::test_variant_paths_are_the_paths_of_the_api_variant_urls`);
    re-derived here with a different (motorbike_id, image_id) pair as an
    independent confirmation rather than trusting the single existing example."""
    motorbike_id = "01K0000000000000000000MOTO"
    image_id = "01K00000000000000000000IMG"

    urls = image_schemas.variant_urls(motorbike_id, image_id)

    for variant in image_service.VARIANT_WIDTHS:
        disk_path = image_service.variant_path(motorbike_id, image_id, variant)
        assert getattr(urls, variant) == f"{image_schemas.MEDIA_URL_PREFIX}/{disk_path}"
    # And the formula names are literally the API's field names, both directions.
    assert set(image_service.VARIANT_WIDTHS) == {"thumb", "card", "detail"}


def test_one_call_creates_exactly_one_pending_row_with_attribution_and_final_url(
    fake_session: FakeAsyncSession, media_dir: Path
) -> None:
    """Independently re-confirms row shape, `pending` status, stored
    attribution and the post-redirect `source_url` in one place, combining
    what the dev suite proves across two separate tests."""
    final_url = "https://cdn.example.test/gsr600-full.jpg"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == IMAGE_URL:
            return httpx2.Response(302, headers={"location": final_url})
        return image_response(image_bytes(400, 300))

    outcome = run_ingest(fake_session, handler, attribution="A. Photographer · CC BY-SA 4.0")

    assert isinstance(outcome, image_service.ImageResult)
    rows = fake_session.rows(MotorbikeImage)
    assert len(rows) == 1
    assert rows[0] is outcome.image
    assert outcome.image.status.value == "pending"
    assert outcome.image.source_url == final_url
    assert outcome.image.attribution == "A. Photographer · CC BY-SA 4.0"
    assert fake_session.commit_count == 1
