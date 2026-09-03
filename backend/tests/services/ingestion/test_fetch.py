"""Tests for `app.services.ingestion.fetch`.

Every request is answered by an `httpx2.MockTransport`, so the limits (size cap,
content type, timeout, redirects) are provable without a network and without
waiting. The politeness delay is driven by an injected clock: the test proves the
wait was requested, it does not spend it.
"""

import asyncio
from collections.abc import AsyncIterator, Callable

import httpx2
import pytest

from app.core.config import get_settings
from app.services.ingestion import fetch

Handler = Callable[[httpx2.Request], httpx2.Response]

URL = "https://example.test/bikes/gsr600"


class RecordingGate(fetch.PolitenessGate):
    """Politeness gate that records hosts instead of waiting for them."""

    def __init__(self) -> None:
        super().__init__(delay_seconds=0.0)
        self.hosts: list[str] = []

    async def wait(self, host: str) -> float:
        self.hosts.append(host)
        return 0.0


class FakeClock:
    """Monotonic clock plus sleep, both under the test's control."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def run_fetch(handler: Handler, url: str = URL) -> fetch.FetchOutcome:
    """Fetch `url` against `handler`, with the politeness delay switched off."""

    async def call() -> fetch.FetchOutcome:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler),
            follow_redirects=True,
            headers={"User-Agent": fetch.USER_AGENT},
        ) as client:
            return await fetch.fetch_html(url, client=client, gate=RecordingGate())

    return asyncio.run(call())


def html_response(body: bytes, *, charset: str = "utf-8") -> httpx2.Response:
    return httpx2.Response(
        200, headers={"content-type": f"text/html; charset={charset}"}, content=body
    )


def test_returns_the_payload_content_type_and_final_url(
    html_fixture: Callable[[str], str],
) -> None:
    page = html_fixture("gsr600_article.html")

    outcome = run_fetch(lambda request: html_response(page.encode()))

    assert isinstance(outcome, fetch.FetchResult)
    assert (outcome.url, outcome.status_code, outcome.content_type) == (URL, 200, "text/html")
    assert outcome.content == page.encode()
    assert "Suzuki GSR600" in outcome.text


def test_sends_the_pinned_user_agent() -> None:
    seen: list[str | None] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers.get("user-agent"))
        return html_response(b"<html><body><p>ok</p></body></html>")

    run_fetch(handler)

    assert seen == [fetch.USER_AGENT]


def test_decodes_a_non_utf8_charset() -> None:
    outcome = run_fetch(
        lambda request: html_response(
            "<html><body>café</body></html>".encode("iso-8859-1"), charset="iso-8859-1"
        )
    )

    assert isinstance(outcome, fetch.FetchResult)
    assert outcome.encoding == "iso-8859-1"
    assert "café" in outcome.text


def test_follows_redirects_and_reports_the_target_url() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/gsr600"):
            return httpx2.Response(301, headers={"location": "https://moved.test/gsr-600"})
        return html_response(b"<html><body><p>moved here</p></body></html>")

    outcome = run_fetch(handler)

    assert isinstance(outcome, fetch.FetchResult)
    assert outcome.url == "https://moved.test/gsr-600"


def test_aborts_a_body_that_exceeds_the_size_cap(
    settings_override: Callable[..., None],
) -> None:
    settings_override(INGESTION_MAX_FETCH_BYTES=500)
    delivered: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        for index in range(100):
            delivered.append(index)
            yield b"x" * 100

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/html"}, content=body())

    outcome = run_fetch(handler)

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.TOO_LARGE
    # The transfer stopped at the cap instead of downloading all 10 000 bytes.
    assert len(delivered) < 100


def test_refuses_a_declared_oversized_body_without_reading_it(
    settings_override: Callable[..., None],
) -> None:
    settings_override(INGESTION_MAX_FETCH_BYTES=500)
    read = False

    async def body() -> AsyncIterator[bytes]:
        nonlocal read
        read = True
        yield b"x" * 5000

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"content-type": "text/html", "content-length": "5000"},
            content=body(),
        )

    outcome = run_fetch(handler)

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.TOO_LARGE
    assert read is False


def test_skips_a_pdf_with_a_typed_failure() -> None:
    outcome = run_fetch(
        lambda request: httpx2.Response(
            200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7"
        )
    )

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.UNSUPPORTED_CONTENT_TYPE
    assert outcome.content_type == "application/pdf"
    assert "application/pdf" in outcome.detail


def test_reports_an_error_status_as_a_typed_failure() -> None:
    outcome = run_fetch(
        lambda request: httpx2.Response(404, headers={"content-type": "text/html"}, content=b"no")
    )

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.HTTP_ERROR
    assert outcome.status_code == 404


def test_reports_a_timeout_as_a_typed_failure() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("too slow", request=request)

    outcome = run_fetch(handler)

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.TIMEOUT


def test_reports_a_connection_failure_as_a_typed_failure() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("unreachable", request=request)

    outcome = run_fetch(handler)

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.NETWORK_ERROR


@pytest.mark.parametrize("url", ["ftp://example.test/file.html", "not-a-url", "https:///nohost"])
def test_refuses_a_non_http_url_without_making_a_request(url: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:  # pragma: no cover
        raise AssertionError("no request may be made")

    outcome = run_fetch(handler, url)

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.INVALID_URL


def test_asks_the_politeness_gate_for_the_host() -> None:
    gate = RecordingGate()

    async def call() -> fetch.FetchOutcome:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(
                lambda request: html_response(b"<html><body><p>ok</p></body></html>")
            )
        ) as client:
            return await fetch.fetch_html("https://Example.TEST:443/page", client=client, gate=gate)

    asyncio.run(call())

    assert gate.hosts == ["example.test"]


def test_politeness_gate_spaces_requests_to_the_same_host() -> None:
    clock = FakeClock()
    gate = fetch.PolitenessGate(1.0, monotonic=clock.monotonic, sleep=clock.sleep)

    async def call() -> None:
        assert await gate.wait("example.test") == 0.0
        assert await gate.wait("example.test") == 1.0
        assert await gate.wait("example.test") == 1.0

    asyncio.run(call())

    assert clock.sleeps == [1.0, 1.0]


def test_politeness_gate_does_not_delay_a_different_host() -> None:
    clock = FakeClock()
    gate = fetch.PolitenessGate(1.0, monotonic=clock.monotonic, sleep=clock.sleep)

    async def call() -> None:
        await gate.wait("example.test")
        assert await gate.wait("other.test") == 0.0

    asyncio.run(call())

    assert clock.sleeps == []


def test_build_client_pins_the_configured_limits() -> None:
    settings = get_settings()

    async def call() -> None:
        async with fetch.build_client() as client:
            assert client.headers["user-agent"] == fetch.USER_AGENT
            assert client.follow_redirects is True
            assert client.timeout.read == settings.ingestion_fetch_timeout_seconds

    asyncio.run(call())


def test_pinned_limits_match_the_phase_contract() -> None:
    settings = get_settings()

    assert fetch.USER_AGENT == "MotorcycleBuyingAdvisor/0.1 (educational project)"
    assert fetch.DOMAIN_DELAY_SECONDS == 1.0
    assert settings.ingestion_fetch_timeout_seconds == 20
    assert settings.ingestion_max_fetch_bytes == 5 * 1024 * 1024
