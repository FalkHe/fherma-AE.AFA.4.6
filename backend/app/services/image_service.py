"""Product images: download one picture, resize it, park it for review.

One call to `ingest_image` is one image: it downloads the bytes, retains them
unmodified, derives the three pinned WebP renditions and creates the
`motorbike_images` row in `pending`. Ingestion calls it **at most once per run**
(pinned in `docs/roadmap/stage-01/phase-2/shared-knowledge.md`); the review UI renders the
newest row.

Two contracts this module must not break:

- **The variant paths are the API's URLs.** `MEDIA_DIR/motorbikes/
  {motorbike_id}/{image_id}_{variant}.webp` is computed independently by
  `app.api.schemas.images.variant_urls` for every response, without touching the
  disk. The formula therefore lives twice on purpose — the API layer stays
  import-free for jobs — and the two must be changed together.
- **A missing image is a warning, never a failure.** Every expected outcome — an
  unreachable host, an HTML error page behind an image URL, a corrupt JPEG — is a
  **returned** `ImageFailure` whose `detail` is ready to be appended to an
  operation message. Only a bug raises here.

The download half deliberately reuses the fetch layer's limits (timeout, 5 MiB
ceiling, politeness gate, User-Agent) and its `FetchFailure` vocabulary, but not
`fetch.fetch_html`, which accepts `text/html` only — same split as the JSON
helpers in `wikipedia.py` and `search.py`.
"""

import asyncio
import io
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx2
from PIL import Image, ImageOps
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.base import new_ulid
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.services.ingestion import fetch

logger = logging.getLogger(__name__)

# Sub-tree of MEDIA_DIR holding one directory per catalogue entry.
MOTORBIKES_DIRECTORY = "motorbikes"

# The pinned variant set: name → maximum width in pixels. The names *are* the
# `{variant}` part of the path formula and the field names of the API's
# `variants` object.
VARIANT_WIDTHS: Mapping[str, int] = {"thumb": 320, "card": 640, "detail": 1280}

VARIANT_FORMAT = "WEBP"
VARIANT_SUFFIX = ".webp"
VARIANT_QUALITY = 80

# Filename part that marks the retained original, so it can never collide with
# a variant name.
ORIGINAL_MARKER = "original"

# Image types we accept and the suffix the retained original is stored with.
# The declared media type is trusted for naming only (the original is never
# served); whether the bytes are really an image is decided by the decoder.
IMAGE_CONTENT_TYPES: Mapping[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

# WebP encodes these directly; anything else is converted first.
_WEBP_MODES = frozenset({"RGB", "RGBA"})


class ImageFailureReason(StrEnum):
    """Why an image ingestion produced no row. Callers branch on this, not text."""

    DOWNLOAD_FAILED = "download_failed"
    """Unreachable, too slow, an error status, or larger than the fetch ceiling."""

    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    """The URL answered with something that is not one of the image types."""

    UNREADABLE_IMAGE = "unreadable_image"
    """The bytes arrived but could not be decoded into the variant set."""


@dataclass(frozen=True, slots=True)
class ImageResult:
    """The stored image: its row plus where its files ended up."""

    image: MotorbikeImage

    original_path: str
    """MEDIA_DIR-relative path of the retained original — the stored column."""

    variant_paths: Mapping[str, str]
    """Variant name → MEDIA_DIR-relative path, one entry per `VARIANT_WIDTHS`."""


@dataclass(frozen=True, slots=True)
class ImageFailure:
    """An image ingestion that produced no row, with a warning-ready `detail`."""

    url: str
    reason: ImageFailureReason
    detail: str


ImageOutcome = ImageResult | ImageFailure


def motorbike_directory(motorbike_id: str) -> str:
    """Return the MEDIA_DIR-relative directory holding one model's images."""
    return str(PurePosixPath(MOTORBIKES_DIRECTORY, motorbike_id))


def variant_path(motorbike_id: str, image_id: str, variant: str) -> str:
    """Return the MEDIA_DIR-relative path of one variant.

    This is the disk half of the pinned formula whose URL half lives in
    `app.api.schemas.images`.
    """
    return str(
        PurePosixPath(motorbike_directory(motorbike_id), f"{image_id}_{variant}{VARIANT_SUFFIX}")
    )


def original_path(motorbike_id: str, image_id: str, suffix: str) -> str:
    """Return the MEDIA_DIR-relative path of the retained original.

    `motorbike_images.original_path` stores exactly this string, so moving or
    remounting the media directory never invalidates a row.
    """
    return str(
        PurePosixPath(motorbike_directory(motorbike_id), f"{image_id}_{ORIGINAL_MARKER}{suffix}")
    )


def resolve(relative_path: str, *, media_dir: Path | None = None) -> Path:
    """Turn a MEDIA_DIR-relative path back into an absolute one."""
    return _media_dir(media_dir) / relative_path


async def ingest_image(
    session: AsyncSession,
    motorbike_id: str,
    image_url: str,
    attribution: str | None = None,
    *,
    client: httpx2.AsyncClient | None = None,
    gate: fetch.PolitenessGate | None = None,
    media_dir: Path | None = None,
) -> ImageOutcome:
    """Download one image for `motorbike_id` and store it awaiting review.

    Args:
        session: Session to create the row in; this function commits.
        motorbike_id: Owning catalogue entry — one media directory per model.
        image_url: Absolute `http`/`https` URL of the picture.
        attribution: Credit line to display with the image, `None` when the
            source carried no usable licence metadata.
        client: Reuse an existing client (see `fetch.build_client`); when
            omitted, one is created and closed around the download.
        gate: Politeness gate to honour; defaults to the process-wide one.
        media_dir: Override the configured MEDIA_DIR (tests, one-off tooling).

    Returns:
        `ImageResult` with the `pending` row, or `ImageFailure` — the caller
        decides how loud a missing image is.
    """
    payload = await _download(image_url, client=client, gate=gate)
    if isinstance(payload, fetch.FetchFailure):
        # Already logged by the download half — translate, do not log twice.
        return ImageFailure(
            url=payload.url,
            reason=_download_reason(payload.reason),
            detail=payload.detail,
        )

    image_id = new_ulid()
    try:
        # Decoding and re-encoding three renditions is CPU work: keep it off the
        # event loop so a large photo cannot stall the worker's other awaits.
        stored = await asyncio.to_thread(
            _write_files, motorbike_id, image_id, payload, media_dir=media_dir
        )
    except (OSError, Image.DecompressionBombError) as error:
        return _report(
            ImageFailure(
                url=payload.url,
                reason=ImageFailureReason.UNREADABLE_IMAGE,
                detail=f"Could not process the image at {payload.url}: {type(error).__name__}.",
            ),
            error,
        )

    image = MotorbikeImage(
        id=image_id,
        motorbike_id=motorbike_id,
        # The post-redirect URL: provenance records what actually answered.
        source_url=payload.url,
        attribution=attribution,
        status=ImageStatus.PENDING,
        original_path=stored.original_path,
    )
    session.add(image)
    await session.commit()

    logger.info("Stored image %s for motorbike %s from %s.", image_id, motorbike_id, payload.url)
    return ImageResult(
        image=image,
        original_path=stored.original_path,
        variant_paths=stored.variant_paths,
    )


@dataclass(frozen=True, slots=True)
class _Payload:
    """Downloaded image bytes and the two things naming them needs."""

    url: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class _StoredFiles:
    """Where one image's files were written, MEDIA_DIR-relative."""

    original_path: str
    variant_paths: Mapping[str, str]


async def _download(
    url: str,
    *,
    client: httpx2.AsyncClient | None,
    gate: fetch.PolitenessGate | None,
) -> _Payload | fetch.FetchFailure:
    """Fetch one image under the pinned limits, or return a typed failure."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in fetch.ALLOWED_SCHEMES or not parts.hostname:
        return _report_download(
            fetch.FetchFailure(
                url=url,
                reason=fetch.FetchFailureReason.INVALID_URL,
                detail=f"Not a fetchable image URL: {url}.",
            )
        )

    if client is None:
        async with fetch.build_client() as owned_client:
            return await _download(url, client=owned_client, gate=gate)

    await (gate or fetch.politeness).wait(parts.hostname.lower())

    try:
        return await _stream(client, url, max_bytes=get_settings().ingestion_max_fetch_bytes)
    except httpx2.TimeoutException as error:
        return _report_download(
            fetch.FetchFailure(
                url=url,
                reason=fetch.FetchFailureReason.TIMEOUT,
                detail=f"Timed out downloading the image at {url}.",
            ),
            error,
        )
    except httpx2.HTTPError as error:
        return _report_download(
            fetch.FetchFailure(
                url=url,
                reason=fetch.FetchFailureReason.NETWORK_ERROR,
                detail=f"Could not download the image at {url}: {type(error).__name__}.",
            ),
            error,
        )


async def _stream(
    client: httpx2.AsyncClient, url: str, *, max_bytes: int
) -> _Payload | fetch.FetchFailure:
    """Run the request, rejecting anything unusable as early as possible."""
    async with client.stream("GET", url) as response:
        final_url = str(response.url)
        content_type = _media_type(response.headers.get("content-type"))

        if response.status_code >= 400:
            return _report_download(
                fetch.FetchFailure(
                    url=final_url,
                    reason=fetch.FetchFailureReason.HTTP_ERROR,
                    detail=f"{url} answered HTTP {response.status_code}.",
                    status_code=response.status_code,
                    content_type=content_type,
                )
            )

        if content_type not in IMAGE_CONTENT_TYPES:
            return _report_download(
                fetch.FetchFailure(
                    url=final_url,
                    reason=fetch.FetchFailureReason.UNSUPPORTED_CONTENT_TYPE,
                    detail=(
                        f"Skipped the image at {url}: content type "
                        f"{content_type or 'unknown'} is not a supported image type."
                    ),
                    status_code=response.status_code,
                    content_type=content_type,
                )
            )

        declared = _declared_length(response.headers.get("content-length"))
        if declared is not None and declared > max_bytes:
            return _report_download(
                fetch.FetchFailure(
                    url=final_url,
                    reason=fetch.FetchFailureReason.TOO_LARGE,
                    detail=(
                        f"Skipped the image at {url}: declared body of {declared} bytes "
                        f"exceeds {max_bytes} bytes."
                    ),
                    status_code=response.status_code,
                    content_type=content_type,
                )
            )

        content = bytearray()
        async for chunk in response.aiter_bytes():
            content += chunk
            if len(content) > max_bytes:
                # Leaving the context manager closes the connection, so the rest
                # of an oversized body is never transferred.
                return _report_download(
                    fetch.FetchFailure(
                        url=final_url,
                        reason=fetch.FetchFailureReason.TOO_LARGE,
                        detail=f"Aborted the image at {url}: body exceeds {max_bytes} bytes.",
                        status_code=response.status_code,
                        content_type=content_type,
                    )
                )

        return _Payload(url=final_url, content_type=content_type, content=bytes(content))


def _write_files(
    motorbike_id: str,
    image_id: str,
    payload: _Payload,
    *,
    media_dir: Path | None,
) -> _StoredFiles:
    """Retain the original and write the variant set; runs in a worker thread."""
    directory = resolve(motorbike_directory(motorbike_id), media_dir=media_dir)
    directory.mkdir(parents=True, exist_ok=True)

    original = original_path(motorbike_id, image_id, IMAGE_CONTENT_TYPES[payload.content_type])
    resolve(original, media_dir=media_dir).write_bytes(payload.content)

    variant_paths: dict[str, str] = {}
    try:
        with Image.open(io.BytesIO(payload.content)) as opened:
            prepared = _prepared(opened)
            for variant, max_width in VARIANT_WIDTHS.items():
                relative = variant_path(motorbike_id, image_id, variant)
                _capped(prepared, max_width).save(
                    resolve(relative, media_dir=media_dir),
                    format=VARIANT_FORMAT,
                    quality=VARIANT_QUALITY,
                )
                variant_paths[variant] = relative
    except Exception:
        # No row will reference these files — remove them instead of leaving
        # orphans behind (the original is written before decoding is attempted).
        for relative in (original, *variant_paths.values()):
            resolve(relative, media_dir=media_dir).unlink(missing_ok=True)
        raise

    logger.info(
        "Wrote %d image variants for %s under %s.",
        len(variant_paths),
        image_id,
        motorbike_directory(motorbike_id),
    )
    return _StoredFiles(original_path=original, variant_paths=variant_paths)


def _prepared(image: Image.Image) -> Image.Image:
    """Return the image upright and in a mode WebP can encode.

    Camera orientation is applied once here rather than per variant, and
    transparency is kept when the source has it instead of being flattened to
    black.
    """
    upright = ImageOps.exif_transpose(image) or image
    if upright.mode in _WEBP_MODES:
        return upright
    return upright.convert("RGBA" if _has_alpha(upright) else "RGB")


def _has_alpha(image: Image.Image) -> bool:
    """Whether the source carries transparency (as a band or as palette info)."""
    return "A" in image.getbands() or "transparency" in image.info


def _capped(image: Image.Image, max_width: int) -> Image.Image:
    """Scale the image down to `max_width`, preserving the aspect ratio.

    A source narrower than the cap is used as it is: a variant is a cap, not a
    target, so a small picture is never upscaled into a blurry one.
    """
    if image.width <= max_width:
        return image
    height = max(1, round(image.height * max_width / image.width))
    return image.resize((max_width, height), Image.Resampling.LANCZOS)


def _download_reason(reason: fetch.FetchFailureReason) -> ImageFailureReason:
    """Map the fetch layer's reason onto the two the caller distinguishes."""
    if reason is fetch.FetchFailureReason.UNSUPPORTED_CONTENT_TYPE:
        return ImageFailureReason.UNSUPPORTED_CONTENT_TYPE
    return ImageFailureReason.DOWNLOAD_FAILED


def _media_type(raw: str | None) -> str:
    """Reduce a `Content-Type` header to its lower-case media type."""
    if not raw:
        return ""
    return raw.split(";", 1)[0].strip().lower()


def _declared_length(raw: str | None) -> int | None:
    """Parse `Content-Length`; a malformed header is simply no information."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _media_dir(override: Path | None) -> Path:
    """The media root: the explicit override, else the configured MEDIA_DIR."""
    return override if override is not None else get_settings().media_dir


def _report_download(
    failure: fetch.FetchFailure, error: Exception | None = None
) -> fetch.FetchFailure:
    """Log one warning about the download half and hand the failure back."""
    logger.warning(
        "Image download failed (%s): %s",
        failure.reason.value,
        failure.detail,
        exc_info=error,
    )
    return failure


def _report(failure: ImageFailure, error: Exception | None = None) -> ImageFailure:
    """Log one warning and hand the typed failure back to the caller."""
    logger.warning(
        "Image ingestion failed (%s): %s",
        failure.reason.value,
        failure.detail,
        exc_info=error,
    )
    return failure
