"""QA coverage for `app.services.ingestion.wikipedia` (step 2.11).

The existing suite (`test_wikipedia.py`) proves the pinned endpoints, params,
matched-title recording, attribution composition and entity handling
thoroughly; the one thing it does not prove is the pinned **User-Agent** on the
JSON API calls when the module builds its own client (`client=None` — the real
code path a bare `wikipedia.lookup(name)` call takes), because every existing
test hands in a pre-built client whose headers already happen to carry it. This
module patches `fetch.build_client` to route through a `MockTransport` instead
of the network, so the assertion is on the header the *module itself* sends.
"""

import asyncio
from typing import Any

import httpx2
import pytest

from app.services.ingestion import fetch, wikipedia

NAME = "Suzuki GSR 600"


class RecordingGate(fetch.PolitenessGate):
    """Politeness gate that records hosts instead of waiting for them."""

    def __init__(self) -> None:
        super().__init__(delay_seconds=0.0)
        self.hosts: list[str] = []

    async def wait(self, host: str) -> float:
        self.hosts.append(host)
        return 0.0


@pytest.fixture
def patched_build_client(
    monkeypatch: pytest.MonkeyPatch,
) -> list[httpx2.Request]:
    """Make `fetch.build_client()` (as the module calls it) use a MockTransport.

    Returns the list every request lands in, so the test can inspect exactly
    what the module sent without ever opening a socket.
    """
    requests: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        path = request.url.path
        if path == "/w/rest.php/v1/search/page":
            return httpx2.Response(
                200,
                json={"pages": [{"key": "Suzuki_GSR600", "title": "Suzuki GSR600"}]},
            )
        if path.startswith("/api/rest_v1/page/summary/"):
            return httpx2.Response(200, json={})  # no image: keeps this test to one call chain
        raise AssertionError(f"unexpected request: {request.url}")

    def fake_build_client(*, timeout_seconds: float | None = None) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.MockTransport(handler),
            follow_redirects=True,
            headers={"User-Agent": fetch.USER_AGENT},
        )

    monkeypatch.setattr(fetch, "build_client", fake_build_client)
    return requests


def test_find_page_sends_the_pinned_user_agent_via_the_modules_own_client(
    patched_build_client: list[httpx2.Request],
) -> None:
    """`find_page(name)` with no injected client must still carry the User-Agent."""

    async def call() -> Any:
        return await wikipedia.find_page(NAME, gate=RecordingGate())

    page = asyncio.run(call())

    assert isinstance(page, wikipedia.WikipediaPage)
    assert len(patched_build_client) == 1
    assert patched_build_client[0].headers.get("user-agent") == fetch.USER_AGENT


def test_find_image_sends_the_pinned_user_agent_via_the_modules_own_client(
    patched_build_client: list[httpx2.Request],
) -> None:
    """The summary lookup (a JSON call) also carries it when self-building a client."""
    page = wikipedia.WikipediaPage(
        key="Suzuki_GSR600",
        title="Suzuki GSR600",
        url="https://en.wikipedia.org/wiki/Suzuki_GSR600",
    )

    async def call() -> Any:
        return await wikipedia.find_image(page, gate=RecordingGate())

    image = asyncio.run(call())

    assert image is None  # the fake summary carries no originalimage
    assert len(patched_build_client) == 1
    assert patched_build_client[0].headers.get("user-agent") == fetch.USER_AGENT
