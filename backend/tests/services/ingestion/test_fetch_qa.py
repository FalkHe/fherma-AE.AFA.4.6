"""QA coverage for `app.services.ingestion.fetch` (steps 2.10/2.11 combined slice).

Targets the specific risks the dev report and shared-knowledge did not already
prove with a test: a `Content-Length` header that understates the real body (the
streamed cap must still catch it, not just the header check), the "sneaky"
content-type values a real server can answer with, and the politeness delay
wired end-to-end through `fetch_html` itself (not only at the `PolitenessGate`
unit level). Everything runs against `httpx2.MockTransport` — never the network.
"""

import asyncio
from collections.abc import AsyncIterator, Callable

import httpx2

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


def run_fetch(
    handler: Handler,
    url: str = URL,
    *,
    gate: fetch.PolitenessGate | None = None,
) -> fetch.FetchOutcome:
    """Fetch `url` against `handler`."""

    async def call() -> fetch.FetchOutcome:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler),
            follow_redirects=True,
            headers={"User-Agent": fetch.USER_AGENT},
        ) as client:
            return await fetch.fetch_html(url, client=client, gate=gate or RecordingGate())

    return asyncio.run(call())


# --- Content-Length lies: the streamed cap is the real enforcement ----------


def test_a_content_length_lie_is_still_caught_by_the_streamed_cap(
    settings_override: Callable[..., None],
) -> None:
    """A small/absent `Content-Length` must not exempt an oversized body.

    The declared-length check only rejects a body that *announces* itself as
    too large; a server that lies (or omits the header) must still be caught
    while the body streams in.
    """
    settings_override(INGESTION_MAX_FETCH_BYTES=500)
    delivered: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        for index in range(100):
            delivered.append(index)
            yield b"x" * 100  # 100 chunks of 100 bytes = 10 000 bytes total.

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            # Understates the real body by an order of magnitude.
            headers={"content-type": "text/html", "content-length": "50"},
            content=body(),
        )

    outcome = run_fetch(handler)

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.TOO_LARGE
    # The transfer stopped once the cap was crossed, not after all 10 000 bytes.
    assert len(delivered) < 100


def test_a_content_length_lie_without_the_header_at_all_is_also_caught(
    settings_override: Callable[..., None],
) -> None:
    """No `Content-Length` header at all defers entirely to the streamed cap."""
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
    assert len(delivered) < 100


# --- Sneaky content-type values ----------------------------------------------


def test_accepts_text_html_with_a_charset_parameter() -> None:
    outcome = run_fetch(
        lambda request: httpx2.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            content=b"<html><body><p>ok</p></body></html>",
        )
    )

    assert isinstance(outcome, fetch.FetchResult)
    assert outcome.content_type == "text/html"


def test_rejects_application_xhtml_xml() -> None:
    """`application/xhtml+xml` is not `text/html` — the pinned contract is exact."""
    outcome = run_fetch(
        lambda request: httpx2.Response(
            200,
            headers={"content-type": "application/xhtml+xml; charset=utf-8"},
            content=b"<html><body><p>ok</p></body></html>",
        )
    )

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.UNSUPPORTED_CONTENT_TYPE
    assert outcome.content_type == "application/xhtml+xml"


def test_rejects_text_plain() -> None:
    outcome = run_fetch(
        lambda request: httpx2.Response(
            200, headers={"content-type": "text/plain"}, content=b"just text"
        )
    )

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.UNSUPPORTED_CONTENT_TYPE
    assert outcome.content_type == "text/plain"


def test_rejects_a_missing_content_type() -> None:
    outcome = run_fetch(
        lambda request: httpx2.Response(200, content=b"<html><body><p>ok</p></body></html>")
    )

    assert isinstance(outcome, fetch.FetchFailure)
    assert outcome.reason is fetch.FetchFailureReason.UNSUPPORTED_CONTENT_TYPE
    assert outcome.content_type == ""
    assert "unknown" in outcome.detail


# --- Politeness, wired through fetch_html end-to-end -------------------------


def test_two_consecutive_fetches_to_the_same_domain_are_delayed() -> None:
    clock = FakeClock()
    gate = fetch.PolitenessGate(1.0, monotonic=clock.monotonic, sleep=clock.sleep)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/html"}, content=b"<p>ok</p>")

    run_fetch(handler, "https://same.test/a", gate=gate)
    run_fetch(handler, "https://same.test/b", gate=gate)

    assert clock.sleeps == [1.0]


def test_fetches_to_different_domains_are_not_delayed() -> None:
    clock = FakeClock()
    gate = fetch.PolitenessGate(1.0, monotonic=clock.monotonic, sleep=clock.sleep)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/html"}, content=b"<p>ok</p>")

    run_fetch(handler, "https://one.test/a", gate=gate)
    run_fetch(handler, "https://two.test/a", gate=gate)

    assert clock.sleeps == []
