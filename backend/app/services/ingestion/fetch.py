"""Fetching one remote HTML page, under fixed limits and with fixed manners.

Every outbound source request in this project goes through `fetch_html`, so the
limits are in one place: a 20 s timeout, a 5 MiB ceiling enforced while the body
streams in (not after it arrived), `text/html` only, redirects followed, one
second between two requests to the same host, and a User-Agent that says who we
are.

Expected failures — a slow server, a 404, a PDF behind an HTML-looking URL, a
multi-hundred-megabyte page — are **returned**, not raised: whether a missing
source is a warning appended to the operation message or the end of the
ingestion run is the caller's decision, not this module's.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

import httpx2

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Pinned identity for every outbound source request (Phase-2 contract).
USER_AGENT = "MotorcycleBuyingAdvisor/0.1 (educational project)"

# The only content type we can extract prose from in Phase 2. PDFs are skipped
# with a warning (Docling is deferred), everything else is not a document.
HTML_CONTENT_TYPE = "text/html"

# Minimum time between two requests to the same host.
DOMAIN_DELAY_SECONDS = 1.0

# Fallback when a response declares no usable charset.
DEFAULT_ENCODING = "utf-8"

ALLOWED_SCHEMES = frozenset({"http", "https"})


class FetchFailureReason(StrEnum):
    """Why a fetch produced no usable HTML. Callers branch on this, not on text."""

    INVALID_URL = "invalid_url"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    HTTP_ERROR = "http_error"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    TOO_LARGE = "too_large"


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A fetched HTML page: the payload to retain plus what it came from."""

    url: str
    """The final URL, after redirects — this is what provenance should record."""

    status_code: int
    content_type: str
    """Media type in lower case, parameters stripped."""

    content: bytes
    """The raw payload, byte-identical to what `storage` writes to disk."""

    encoding: str

    @property
    def text(self) -> str:
        """The payload decoded for extraction; undecodable bytes are replaced.

        A single bad byte in a long article must not cost us the article, so
        decoding never fails.
        """
        try:
            return self.content.decode(self.encoding, errors="replace")
        except LookupError:
            return self.content.decode(DEFAULT_ENCODING, errors="replace")


@dataclass(frozen=True, slots=True)
class FetchFailure:
    """A fetch that produced no usable HTML, with a warning-ready `detail`."""

    url: str
    reason: FetchFailureReason
    detail: str
    status_code: int | None = None
    content_type: str | None = None


FetchOutcome = FetchResult | FetchFailure


class PolitenessGate:
    """Spaces requests to the same host at least `delay_seconds` apart.

    Slots are reserved under the lock and awaited outside it, so two fetches to
    different hosts never wait for each other while two fetches to the same host
    always do. The clock and the sleep are injected because a test must be able
    to prove the delay without spending it.
    """

    def __init__(
        self,
        delay_seconds: float = DOMAIN_DELAY_SECONDS,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._delay_seconds = delay_seconds
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def wait(self, host: str) -> float:
        """Wait until this host may be requested again; return the time waited."""
        async with self._lock:
            now = self._monotonic()
            earliest = max(now, self._next_allowed.get(host, now))
            self._next_allowed[host] = earliest + self._delay_seconds
            waited = earliest - now

        if waited > 0:
            await self._sleep(waited)
        return waited


# Process-wide gate: politeness is a property of the host we talk to, not of the
# call site, so every caller shares one.
politeness = PolitenessGate()


def build_client(*, timeout_seconds: float | None = None) -> httpx2.AsyncClient:
    """Return an HTTPX client configured with the pinned fetch limits.

    Callers fetching several pages should build one client and pass it to every
    `fetch_html` call, so connections and DNS lookups are reused.
    """
    settings = get_settings()
    return httpx2.AsyncClient(
        timeout=httpx2.Timeout(
            timeout_seconds
            if timeout_seconds is not None
            else settings.ingestion_fetch_timeout_seconds
        ),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


async def fetch_html(
    url: str,
    *,
    client: httpx2.AsyncClient | None = None,
    gate: PolitenessGate | None = None,
) -> FetchOutcome:
    """Fetch one page and return its HTML payload or a typed failure.

    Args:
        url: Absolute `http`/`https` URL.
        client: Reuse an existing client (see `build_client`); when omitted, a
            client with the pinned limits is created and closed around the call.
        gate: Politeness gate to honour; defaults to the process-wide one.
    """
    scheme_failure = _reject_unusable_url(url)
    if scheme_failure is not None:
        return _report(scheme_failure)

    if client is None:
        async with build_client() as owned_client:
            return await fetch_html(url, client=owned_client, gate=gate)

    await (gate or politeness).wait(_host(url))

    max_bytes = get_settings().ingestion_max_fetch_bytes
    try:
        return await _stream(client, url, max_bytes=max_bytes)
    except httpx2.TimeoutException as error:
        return _report(
            FetchFailure(
                url=url,
                reason=FetchFailureReason.TIMEOUT,
                detail=f"Timed out fetching {url}.",
            ),
            error,
        )
    except httpx2.HTTPError as error:
        return _report(
            FetchFailure(
                url=url,
                reason=FetchFailureReason.NETWORK_ERROR,
                detail=f"Could not fetch {url}: {type(error).__name__}.",
            ),
            error,
        )
    except httpx2.InvalidURL as error:
        return _report(
            FetchFailure(
                url=url,
                reason=FetchFailureReason.INVALID_URL,
                detail=f"Not a fetchable URL: {url}.",
            ),
            error,
        )


async def _stream(client: httpx2.AsyncClient, url: str, *, max_bytes: int) -> FetchOutcome:
    """Run the request, applying every limit as early as it can be applied."""
    async with client.stream("GET", url) as response:
        final_url = str(response.url)
        content_type = _media_type(response.headers.get("content-type"))

        if response.status_code >= 400:
            return _report(
                FetchFailure(
                    url=final_url,
                    reason=FetchFailureReason.HTTP_ERROR,
                    detail=f"{url} answered HTTP {response.status_code}.",
                    status_code=response.status_code,
                    content_type=content_type,
                )
            )

        if content_type != HTML_CONTENT_TYPE:
            return _report(
                FetchFailure(
                    url=final_url,
                    reason=FetchFailureReason.UNSUPPORTED_CONTENT_TYPE,
                    detail=(
                        f"Skipped {url}: content type {content_type or 'unknown'} "
                        f"is not {HTML_CONTENT_TYPE}."
                    ),
                    status_code=response.status_code,
                    content_type=content_type,
                )
            )

        too_large = _too_large_failure(
            _declared_length(response.headers.get("content-length")),
            url=url,
            final_url=final_url,
            status_code=response.status_code,
            content_type=content_type,
            max_bytes=max_bytes,
        )
        if too_large is not None:
            return _report(too_large)

        content = bytearray()
        async for chunk in response.aiter_bytes():
            content += chunk
            if len(content) > max_bytes:
                # Leaving the context manager closes the connection, so the rest
                # of an oversized body is never transferred.
                return _report(
                    FetchFailure(
                        url=final_url,
                        reason=FetchFailureReason.TOO_LARGE,
                        detail=f"Aborted {url}: body exceeds {max_bytes} bytes.",
                        status_code=response.status_code,
                        content_type=content_type,
                    )
                )

        return FetchResult(
            url=final_url,
            status_code=response.status_code,
            content_type=content_type,
            content=bytes(content),
            encoding=_encoding(response),
        )


def _reject_unusable_url(url: str) -> FetchFailure | None:
    """Refuse anything that is not an absolute http(s) URL before we open a socket."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES or not parts.hostname:
        return FetchFailure(
            url=url,
            reason=FetchFailureReason.INVALID_URL,
            detail=f"Not a fetchable URL: {url}.",
        )
    return None


def _too_large_failure(
    declared_length: int | None,
    *,
    url: str,
    final_url: str,
    status_code: int,
    content_type: str,
    max_bytes: int,
) -> FetchFailure | None:
    """Reject an oversized body already announced by `Content-Length`."""
    if declared_length is None or declared_length <= max_bytes:
        return None
    return FetchFailure(
        url=final_url,
        reason=FetchFailureReason.TOO_LARGE,
        detail=(
            f"Skipped {url}: declared body of {declared_length} bytes exceeds {max_bytes} bytes."
        ),
        status_code=status_code,
        content_type=content_type,
    )


def _declared_length(raw: str | None) -> int | None:
    """Parse `Content-Length`; a malformed header is simply no information."""
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _media_type(raw: str | None) -> str:
    """Reduce a `Content-Type` header to its lower-case media type."""
    if not raw:
        return ""
    return raw.split(";", 1)[0].strip().lower()


def _encoding(response: httpx2.Response) -> str:
    """Charset declared by the response, or UTF-8 when it declares none."""
    return response.charset_encoding or DEFAULT_ENCODING


def _host(url: str) -> str:
    """Politeness key: the host, case-normalized, port and userinfo dropped."""
    return (urlsplit(url).hostname or "").lower()


def _report(failure: FetchFailure, error: Exception | None = None) -> FetchFailure:
    """Log one structured warning and hand the failure back to the caller."""
    logger.warning(
        "Source fetch failed (%s): %s",
        failure.reason.value,
        failure.detail,
        exc_info=error,
    )
    return failure
