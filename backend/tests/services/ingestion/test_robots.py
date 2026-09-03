"""Tests for `app.services.ingestion.robots` (step 6.21, D8/D12).

Every `robots.txt` fetch is answered by an `httpx2.MockTransport`, so the
pinned outcome table is provable without a network and without waiting — the
politeness delay is driven by an injected clock, exactly like
`tests/services/ingestion/test_fetch.py`.
"""

import asyncio
from collections.abc import Callable

import httpx2
import pytest

from app.services.ingestion import fetch, robots

Handler = Callable[[httpx2.Request], httpx2.Response]

URL = "https://example.test/bikes/gsr600"


class RecordingGate(fetch.PolitenessGate):
    """Politeness gate that records the hosts it was asked to wait for."""

    def __init__(self) -> None:
        super().__init__(delay_seconds=0.0)
        self.hosts: list[str] = []

    async def wait(self, host: str) -> float:
        self.hosts.append(host)
        return 0.0


def _gate(handler: Handler, url: str = URL, *, gate: fetch.PolitenessGate | None = None) -> bool:
    """Run one `RobotsGate.allows(url)` call against `handler`.

    Defaults to a zero-delay `RecordingGate`, never the real process-wide
    `fetch.politeness` singleton — a test that wants to prove the default-gate
    behaviour itself passes `gate=None` explicitly through `RobotsGate` (see
    `test_a_missing_gate_defaults_to_the_process_wide_politeness_gate` below).
    """

    async def call() -> bool:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            return await robots.RobotsGate(client=client, gate=gate or RecordingGate()).allows(url)

    return asyncio.run(call())


def robots_txt_response(body: bytes, *, status_code: int = 200) -> httpx2.Response:
    return httpx2.Response(status_code, content=body)


# --- the pinned outcome table --------------------------------------------------


def test_a_2xx_robots_txt_is_parsed_and_answers_can_fetch() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"User-agent: *\nDisallow: /bikes/\n")

    assert _gate(handler) is False


def test_a_2xx_robots_txt_allows_a_path_it_does_not_disallow() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"User-agent: *\nDisallow: /other/\n")

    assert _gate(handler) is True


@pytest.mark.parametrize("status_code", [401, 403])
def test_401_and_403_disallow_the_host(status_code: int) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"", status_code=status_code)

    assert _gate(handler) is False


@pytest.mark.parametrize("status_code", [404, 410])
def test_other_4xx_allows_the_host_with_no_published_policy(status_code: int) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"", status_code=status_code)

    assert _gate(handler) is True


def test_a_5xx_disallows_the_host_conservatively() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"", status_code=500)

    assert _gate(handler) is False


def test_a_timeout_disallows_the_host_conservatively() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("too slow", request=request)

    assert _gate(handler) is False


def test_a_network_error_disallows_the_host_conservatively() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("unreachable", request=request)

    assert _gate(handler) is False


def test_a_refused_host_logs_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"", status_code=403)

    with caplog.at_level("WARNING", logger="app.services.ingestion.robots"):
        _gate(handler)

    assert len(caplog.records) == 1
    assert "example.test" in caplog.messages[0]


# --- per-host caching -----------------------------------------------------------


def test_the_robots_txt_of_one_host_is_fetched_only_once() -> None:
    fetched: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        fetched.append(str(request.url))
        return robots_txt_response(b"User-agent: *\nDisallow: /private/\n")

    async def call() -> tuple[bool, bool]:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            gate = robots.RobotsGate(client=client, gate=RecordingGate())
            first = await gate.allows("https://example.test/bikes/gsr600")
            second = await gate.allows("https://example.test/bikes/other")
            return first, second

    first, second = asyncio.run(call())

    assert (first, second) == (True, True)
    assert fetched == ["https://example.test/robots.txt"]


def test_a_refused_host_stays_refused_without_a_second_fetch() -> None:
    fetched: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        fetched.append(str(request.url))
        return robots_txt_response(b"", status_code=403)

    async def call() -> tuple[bool, bool]:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            gate = robots.RobotsGate(client=client, gate=RecordingGate())
            first = await gate.allows("https://example.test/bikes/gsr600")
            second = await gate.allows("https://example.test/bikes/other")
            return first, second

    first, second = asyncio.run(call())

    assert (first, second) == (False, False)
    assert len(fetched) == 1


# --- politeness ------------------------------------------------------------------


def test_the_politeness_gate_is_awaited_before_the_first_fetch_of_a_host() -> None:
    gate = RecordingGate()

    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"")

    _gate(handler, gate=gate)

    assert gate.hosts == ["example.test"]


def test_a_missing_gate_defaults_to_the_process_wide_politeness_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors `fetch.fetch_html`'s own `gate or politeness` default."""
    waited: list[str] = []
    real_wait = fetch.politeness.wait

    async def spy(host: str) -> float:
        waited.append(host)
        return await real_wait(host)

    monkeypatch.setattr(fetch.politeness, "wait", spy)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return robots_txt_response(b"")

    async def call() -> bool:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handler)) as client:
            # `gate` omitted entirely, not merely `None` through a helper.
            return await robots.RobotsGate(client=client).allows(URL)

    assert asyncio.run(call()) is True
    assert waited == ["example.test"]
