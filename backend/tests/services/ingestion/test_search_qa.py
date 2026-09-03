"""QA coverage for `app.services.ingestion.search` (follow-up: openrouter provider).

The dev suite (`test_search.py`) proves the happy path, the missing-key
warning, the pinned call shape, the citation parsing, the utm_source
stripping, the cap/dedupe interplay and one HTTP-error failure mode for both
providers. This file targets what it did not cover for the risks called out
in the QA briefing:

- an invalid `SEARCH_PROVIDER` value must fail settings loading, not silently
  fall back to Tavily;
- the other two failure shapes a real network call can produce besides an
  HTTP error status — a timeout and a transport-level error — must warn and
  not raise, for the new OpenRouter provider specifically (its `_post` is a
  near-duplicate of Tavily's, so a bug there is exactly the kind a copy-paste
  slice can introduce; the dev suite only exercised HTTP >= 400 for it);
- a non-JSON response body must warn and not raise;
- the API key must reach the OpenRouter provider only via the `Authorization`
  header and never appear in a log record, and the attribution headers
  (`HTTP-Referer`/`X-Title`) pinned by the shared-knowledge contract must be
  present on the wire;
- only `utm_source` is stripped even when other utm-ish parameters
  (`utm_medium`, `utm_campaign`) are present alongside it.

Everything runs against `httpx2.MockTransport` or raises directly from the
handler — never the network.
"""

import json
import logging
from collections.abc import Callable

import httpx2
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.models.source_document import SourceType
from app.llm.models import APP_TITLE, APP_URL
from app.services.ingestion import search

from .test_search import (
    NAME,
    PRODUCT_QUERY,
    TECHNICAL_QUERY,
    RecordingGate,
    _default_openrouter_script,
)

API_KEY = "sk-super-secret-key"


def test_invalid_search_provider_is_rejected_at_settings_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pydantic must reject a provider outside `SearchProviderName`, not accept it."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@127.0.0.1:5432/test")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("SEARCH_PROVIDER", "google")

    with pytest.raises(ValidationError):
        Settings()


def _run(
    provider: search.OpenRouterSearchProvider,
    handle: Callable[[httpx2.Request], httpx2.Response],
) -> search.SearchResults:
    import asyncio

    async def call() -> search.SearchResults:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as client:
            return await provider.search(NAME, client=client, gate=RecordingGate())

    return asyncio.run(call())


@pytest.fixture
def provider() -> search.OpenRouterSearchProvider:
    return search.OpenRouterSearchProvider(api_key=API_KEY)


def test_openrouter_a_timeout_warns_and_the_others_still_run(
    provider: search.OpenRouterSearchProvider,
) -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        if PRODUCT_QUERY in content:
            raise httpx2.TimeoutException("timed out", request=request)
        script = _default_openrouter_script()
        for query, payload in script.items():
            if query in content:
                return httpx2.Response(200, json=payload)
        raise AssertionError("unexpected query")

    results = _run(provider, handle)

    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.TECHNICAL,
        SourceType.TECHNICAL,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert len(results.warnings) == 1
    assert results.warnings[0] == f"Web search for {PRODUCT_QUERY} failed."


def test_openrouter_a_transport_error_warns_and_the_others_still_run(
    provider: search.OpenRouterSearchProvider,
) -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        if TECHNICAL_QUERY in content:
            raise httpx2.ConnectError("unreachable", request=request)
        script = _default_openrouter_script()
        for query, payload in script.items():
            if query in content:
                return httpx2.Response(200, json=payload)
        raise AssertionError("unexpected query")

    results = _run(provider, handle)

    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.PRODUCT,
        SourceType.PRODUCT,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert len(results.warnings) == 1
    assert results.warnings[0] == f"Web search for {TECHNICAL_QUERY} failed."


def test_openrouter_a_non_json_body_warns_and_does_not_raise(
    provider: search.OpenRouterSearchProvider,
) -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        if PRODUCT_QUERY in content:
            return httpx2.Response(200, content=b"<html>not json</html>")
        script = _default_openrouter_script()
        for query, payload in script.items():
            if query in content:
                return httpx2.Response(200, json=payload)
        raise AssertionError("unexpected query")

    results = _run(provider, handle)

    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.TECHNICAL,
        SourceType.TECHNICAL,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert results.warnings == (f"Web search for {PRODUCT_QUERY} failed.",)


def test_openrouter_key_never_appears_in_a_log_record(
    provider: search.OpenRouterSearchProvider,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The key must reach the wire only via the Authorization header."""
    server_script = _default_openrouter_script()

    def handle(request: httpx2.Request) -> httpx2.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        for query, payload in server_script.items():
            if query in content:
                return httpx2.Response(200, json=payload)
        raise AssertionError("unexpected query")

    with caplog.at_level(logging.DEBUG, logger="app.services.ingestion.search"):
        _run(provider, handle)

    for record in caplog.records:
        assert API_KEY not in record.getMessage()


def test_openrouter_missing_key_warning_never_logs_a_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import asyncio

    def handle(request: httpx2.Request) -> httpx2.Response:  # pragma: no cover
        raise AssertionError("no request may be made without a key")

    async def call() -> search.SearchResults:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as client:
            return await search.OpenRouterSearchProvider(api_key="").search(
                NAME, client=client, gate=RecordingGate()
            )

    with caplog.at_level(logging.DEBUG, logger="app.services.ingestion.search"):
        results = asyncio.run(call())

    assert results.warnings == ("Web search skipped: OPENROUTER_API_KEY is not configured.",)
    assert "OPENROUTER_API_KEY" in caplog.text  # the name, never a value, is fine to log
    for record in caplog.records:
        assert record.getMessage().count("=") == 0  # no accidental key=value logging


def test_openrouter_sends_the_pinned_attribution_headers(
    provider: search.OpenRouterSearchProvider,
) -> None:
    server_script = _default_openrouter_script()
    seen: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        content = json.loads(request.content)["messages"][0]["content"]
        for query, payload in server_script.items():
            if query in content:
                return httpx2.Response(200, json=payload)
        raise AssertionError("unexpected query")

    _run(provider, handle)

    request = seen[0]
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    assert request.headers["http-referer"] == APP_URL
    assert request.headers["x-title"] == APP_TITLE
    # The key lives only in the Authorization header, never in the URL or body.
    assert API_KEY not in str(request.url)
    assert API_KEY.encode() not in request.content


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        pytest.param(
            "https://suzuki.test/gsr600?utm_source=openai&utm_medium=web&utm_campaign=x",
            "https://suzuki.test/gsr600?utm_medium=web&utm_campaign=x",
            id="utm_source-among-other-utm-params",
        ),
        pytest.param(
            "https://suzuki.test/gsr600?utm_medium=web&utm_source=openai",
            "https://suzuki.test/gsr600?utm_medium=web",
            id="utm_source-not-first",
        ),
        pytest.param(
            "https://suzuki.test/gsr600",
            "https://suzuki.test/gsr600",
            id="no-utm_source-at-all-is-untouched",
        ),
    ],
)
def test_without_utm_source_strips_only_that_parameter(url: str, expected: str) -> None:
    """Only `utm_source` is removed, even when sibling `utm_*` params are present."""
    assert search._without_utm_source(url) == expected
