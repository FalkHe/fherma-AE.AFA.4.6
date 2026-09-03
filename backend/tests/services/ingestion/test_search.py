"""Tests for `app.services.ingestion.search`.

Both provider APIs are answered by an `httpx2.MockTransport` built from a
per-query script, so the pinned call shapes (Bearer auth, body members, two
results per query) and the pinned result handling (source-type labelling,
dedupe, cap, missing-key warning) are provable without a network and without a
key. The OpenRouter provider adds its citation-annotation parsing and the
`utm_source` stripping to that list — still no live call.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from app.db.models.source_document import SourceType
from app.services.ingestion import fetch, search

NAME = "Suzuki GSR 600"
API_KEY = "test-key"

PRODUCT_QUERY = f'"{NAME}" motorcycle official specifications'
TECHNICAL_QUERY = f'"{NAME}" technical data specifications'
MAGAZINE_QUERY = f'"{NAME}" review test'


class RecordingGate(fetch.PolitenessGate):
    """Politeness gate that records hosts instead of waiting for them."""

    def __init__(self) -> None:
        super().__init__(delay_seconds=0.0)
        self.hosts: list[str] = []

    async def wait(self, host: str) -> float:
        self.hosts.append(host)
        return 0.0


class FakeTavily:
    """Answers each query with a scripted result list; records every request."""

    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script if script is not None else _default_script()
        self.status: dict[str, int] = {}
        self.requests: list[httpx2.Request] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Return the scripted response for the posted query."""
        self.requests.append(request)
        body = json.loads(request.content)
        query = body["query"]

        status = self.status.get(query, 200)
        if status != 200:
            return httpx2.Response(status, json={"detail": "nope"})

        results = self.script.get(query)
        if results is None:
            raise AssertionError(f"unexpected query: {query}")
        return httpx2.Response(200, json={"query": query, "results": results})

    @property
    def queries(self) -> list[str]:
        """The queries that were actually sent, in order."""
        return [json.loads(request.content)["query"] for request in self.requests]


def _result(url: str, title: str) -> dict[str, Any]:
    """One Tavily result, including the members we deliberately ignore."""
    return {
        "url": url,
        "title": title,
        "content": "Snippet we never store — we fetch the page ourselves.",
        "score": 0.9,
    }


def _default_script() -> dict[str, list[dict[str, Any]]]:
    """Two distinct results per pinned query."""
    return {
        PRODUCT_QUERY: [
            _result("https://suzuki.test/gsr600", "GSR600 | Suzuki"),
            _result("https://suzuki.test/gsr600/specs", "GSR600 specifications"),
        ],
        TECHNICAL_QUERY: [
            _result("https://bikez.test/gsr600", "Suzuki GSR600 technical data"),
            _result("https://motodata.test/gsr600", "GSR600 data sheet"),
        ],
        MAGAZINE_QUERY: [
            _result("https://mcn.test/gsr600-review", "Suzuki GSR600 review"),
            _result("https://visordown.test/gsr600", "GSR600 road test"),
        ],
    }


class FakeOpenRouter:
    """Answers each query with a scripted chat completion; records every request."""

    PROMPT_PREFIX = "Find and cite current web pages for this search: "
    PROMPT_SUFFIX = ". List the best sources with their URLs."

    def __init__(self, script: dict[str, Any] | None = None) -> None:
        self.script = script if script is not None else _default_openrouter_script()
        self.status: dict[str, int] = {}
        self.requests: list[httpx2.Request] = []

    @classmethod
    def query_of(cls, request: httpx2.Request) -> str:
        """The search query carried by one posted prompt."""
        content = json.loads(request.content)["messages"][0]["content"]
        return content.removeprefix(cls.PROMPT_PREFIX).removesuffix(cls.PROMPT_SUFFIX)

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Return the scripted completion for the posted query."""
        self.requests.append(request)
        query = self.query_of(request)

        status = self.status.get(query, 200)
        if status != 200:
            return httpx2.Response(status, json={"error": {"message": "nope"}})

        payload = self.script.get(query)
        if payload is None:
            raise AssertionError(f"unexpected query: {query}")
        return httpx2.Response(200, json=payload)

    @property
    def queries(self) -> list[str]:
        """The queries that were actually sent, in order."""
        return [self.query_of(request) for request in self.requests]


def _completion(*citations: dict[str, Any]) -> dict[str, Any]:
    """One OpenRouter completion, including the members we deliberately ignore."""
    return {
        "id": "gen-test",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Prose we never store — we fetch the pages ourselves.",
                    "annotations": [
                        {"type": "url_citation", "url_citation": citation} for citation in citations
                    ],
                }
            }
        ],
    }


def _citation(url: str, title: str) -> dict[str, Any]:
    """One `url_citation`, tagged the way OpenRouter tags cited URLs."""
    return {
        "url": f"{url}?utm_source=openai",
        "title": title,
        "content": "Snippet we never store.",
        "start_index": 0,
        "end_index": 10,
    }


def _default_openrouter_script() -> dict[str, Any]:
    """Two distinct citations per pinned query."""
    return {
        PRODUCT_QUERY: _completion(
            _citation("https://suzuki.test/gsr600", "GSR600 | Suzuki"),
            _citation("https://suzuki.test/gsr600/specs", "GSR600 specifications"),
        ),
        TECHNICAL_QUERY: _completion(
            _citation("https://bikez.test/gsr600", "Suzuki GSR600 technical data"),
            _citation("https://motodata.test/gsr600", "GSR600 data sheet"),
        ),
        MAGAZINE_QUERY: _completion(
            _citation("https://mcn.test/gsr600-review", "Suzuki GSR600 review"),
            _citation("https://visordown.test/gsr600", "GSR600 road test"),
        ),
    }


def run(
    provider: search.SearchProvider,
    server: FakeTavily | FakeOpenRouter,
    *,
    gate: RecordingGate | None = None,
    templates: tuple[search.QueryTemplate, ...] | None = None,
) -> search.SearchResults:
    """Run one provider search against the scripted API."""

    async def call() -> search.SearchResults:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(server.handle),
            headers={"User-Agent": fetch.USER_AGENT},
        ) as client:
            kwargs: dict[str, Any] = {}
            if templates is not None:
                kwargs["templates"] = templates
            return await provider.search(
                NAME, client=client, gate=gate or RecordingGate(), **kwargs
            )

    return asyncio.run(call())


@pytest.fixture
def provider() -> search.TavilySearchProvider:
    """A provider with an explicit key, so no test depends on the environment."""
    return search.TavilySearchProvider(api_key=API_KEY)


def test_runs_the_three_pinned_queries_and_labels_their_results(
    provider: search.TavilySearchProvider,
) -> None:
    server = FakeTavily()

    results = run(provider, server)

    assert server.queries == [PRODUCT_QUERY, TECHNICAL_QUERY, MAGAZINE_QUERY]
    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.PRODUCT,
        SourceType.PRODUCT,
        SourceType.TECHNICAL,
        SourceType.TECHNICAL,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert results.candidates[0].url == "https://suzuki.test/gsr600"
    assert results.candidates[0].title == "GSR600 | Suzuki"
    assert results.warnings == ()


def test_sends_the_pinned_tavily_call_shape(provider: search.TavilySearchProvider) -> None:
    server = FakeTavily()

    run(provider, server)

    request = server.requests[0]
    assert (request.method, str(request.url)) == ("POST", "https://api.tavily.com/search")
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    body = json.loads(request.content)
    # Exactly these three members: raw content is never requested.
    assert body == {
        "query": PRODUCT_QUERY,
        "max_results": 2,
        "search_depth": "basic",
    }


def test_takes_only_the_top_two_results_of_a_query(
    provider: search.TavilySearchProvider,
) -> None:
    script = _default_script()
    script[PRODUCT_QUERY] = [
        _result(f"https://suzuki.test/page-{index}", f"Page {index}") for index in range(5)
    ]
    server = FakeTavily(script)

    results = run(provider, server)

    product_urls = [
        candidate.url
        for candidate in results.candidates
        if candidate.source_type is SourceType.PRODUCT
    ]
    assert product_urls == ["https://suzuki.test/page-0", "https://suzuki.test/page-1"]


def test_dedupes_candidates_by_url_keeping_the_first_label(
    provider: search.TavilySearchProvider,
) -> None:
    script = _default_script()
    script[TECHNICAL_QUERY][0] = _result("https://suzuki.test/gsr600", "Same page again")
    server = FakeTavily(script)

    results = run(provider, server)

    urls = [candidate.url for candidate in results.candidates]
    assert len(urls) == len(set(urls)) == 5
    duplicate = next(c for c in results.candidates if c.url == "https://suzuki.test/gsr600")
    assert duplicate.source_type is SourceType.PRODUCT


def test_caps_the_candidates_at_the_configured_maximum(
    provider: search.TavilySearchProvider,
    settings_override: Callable[..., None],
) -> None:
    settings_override(INGESTION_MAX_WEB_DOCUMENTS=3)
    server = FakeTavily()

    results = run(provider, server)

    assert len(results.candidates) == 3
    # The cap is reached before the third query, so that credit is not spent.
    assert server.queries == [PRODUCT_QUERY, TECHNICAL_QUERY]


def test_a_failed_query_warns_and_the_others_still_run(
    provider: search.TavilySearchProvider,
) -> None:
    server = FakeTavily()
    server.status[TECHNICAL_QUERY] = 500

    results = run(provider, server)

    assert len(results.candidates) == 4
    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.PRODUCT,
        SourceType.PRODUCT,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert len(results.warnings) == 1
    assert TECHNICAL_QUERY in results.warnings[0]


def test_a_missing_api_key_warns_and_makes_no_request(
    settings_override: Callable[..., None],
) -> None:
    settings_override(TAVILY_API_KEY="")

    def handle(request: httpx2.Request) -> httpx2.Response:  # pragma: no cover
        raise AssertionError("no request may be made without a key")

    async def call() -> search.SearchResults:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as client:
            return await search.TavilySearchProvider().search(
                NAME, client=client, gate=RecordingGate()
            )

    results = asyncio.run(call())

    assert results.candidates == ()
    assert results.warnings == ("Web search skipped: TAVILY_API_KEY is not configured.",)


def test_uses_the_configured_key_when_none_is_injected(
    settings_override: Callable[..., None],
) -> None:
    settings_override(TAVILY_API_KEY="from-settings")
    server = FakeTavily()

    run(search.TavilySearchProvider(), server)

    assert server.requests[0].headers["authorization"] == "Bearer from-settings"


def test_ignores_results_without_a_url_and_falls_back_to_the_url_as_title(
    provider: search.TavilySearchProvider,
) -> None:
    script = _default_script()
    script[PRODUCT_QUERY] = [
        {"title": "No URL here", "content": "…"},
        {"url": "https://suzuki.test/untitled"},
    ]
    server = FakeTavily(script)

    results = run(provider, server)

    untitled = results.candidates[0]
    assert untitled.url == "https://suzuki.test/untitled"
    assert untitled.title == "https://suzuki.test/untitled"


def test_a_response_without_results_yields_no_candidates(
    provider: search.TavilySearchProvider,
) -> None:
    script = _default_script()
    script[PRODUCT_QUERY] = []
    server = FakeTavily(script)

    results = run(provider, server)

    assert len(results.candidates) == 4
    assert results.warnings == ()


def test_every_query_passes_through_the_politeness_gate(
    provider: search.TavilySearchProvider,
) -> None:
    gate = RecordingGate()

    run(provider, FakeTavily(), gate=gate)

    assert gate.hosts == ["api.tavily.com"] * 3


def test_get_search_provider_returns_the_configured_provider() -> None:
    provider = search.get_search_provider()

    assert isinstance(provider, search.TavilySearchProvider)
    assert provider.name == "tavily"


@pytest.fixture
def openrouter_provider() -> search.OpenRouterSearchProvider:
    """A provider with an explicit key, so no test depends on the environment."""
    return search.OpenRouterSearchProvider(api_key=API_KEY)


def test_openrouter_runs_the_three_pinned_queries_and_labels_their_results(
    openrouter_provider: search.OpenRouterSearchProvider,
) -> None:
    server = FakeOpenRouter()

    results = run(openrouter_provider, server)

    assert server.queries == [PRODUCT_QUERY, TECHNICAL_QUERY, MAGAZINE_QUERY]
    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.PRODUCT,
        SourceType.PRODUCT,
        SourceType.TECHNICAL,
        SourceType.TECHNICAL,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert results.candidates[0].title == "GSR600 | Suzuki"
    assert results.warnings == ()


def test_openrouter_sends_the_pinned_call_shape(
    openrouter_provider: search.OpenRouterSearchProvider,
    settings_override: Callable[..., None],
) -> None:
    settings_override(CHAT_MODEL="test/search-model")
    server = FakeOpenRouter()

    run(openrouter_provider, server)

    request = server.requests[0]
    assert (request.method, str(request.url)) == (
        "POST",
        "https://openrouter.ai/api/v1/chat/completions",
    )
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "test/search-model"
    assert body["plugins"] == [{"id": "web", "max_results": search.RESULTS_PER_TEMPLATE}]
    assert PRODUCT_QUERY in body["messages"][0]["content"]


def test_openrouter_strips_utm_source_and_keeps_other_query_parameters(
    openrouter_provider: search.OpenRouterSearchProvider,
) -> None:
    script = _default_openrouter_script()
    script[PRODUCT_QUERY] = _completion(
        {"url": "https://suzuki.test/gsr600?utm_source=openai", "title": "Plain"},
        {"url": "https://bikez.test/m.php?model=gsr600&utm_source=openai", "title": "Kept"},
    )
    server = FakeOpenRouter(script)

    results = run(openrouter_provider, server)

    assert [candidate.url for candidate in results.candidates[:2]] == [
        "https://suzuki.test/gsr600",
        "https://bikez.test/m.php?model=gsr600",
    ]


def test_openrouter_dedupes_on_the_cleaned_url_keeping_the_first_label(
    openrouter_provider: search.OpenRouterSearchProvider,
) -> None:
    script = _default_openrouter_script()
    script[TECHNICAL_QUERY] = _completion(
        {"url": "https://suzuki.test/gsr600?utm_source=openai", "title": "Same page again"},
        _citation("https://motodata.test/gsr600", "GSR600 data sheet"),
    )
    server = FakeOpenRouter(script)

    results = run(openrouter_provider, server)

    urls = [candidate.url for candidate in results.candidates]
    assert len(urls) == len(set(urls)) == 5
    duplicate = next(c for c in results.candidates if c.url == "https://suzuki.test/gsr600")
    assert duplicate.source_type is SourceType.PRODUCT


def test_openrouter_takes_only_the_first_two_annotations_and_caps_the_total(
    openrouter_provider: search.OpenRouterSearchProvider,
    settings_override: Callable[..., None],
) -> None:
    settings_override(INGESTION_MAX_WEB_DOCUMENTS=3)
    script = _default_openrouter_script()
    script[PRODUCT_QUERY] = _completion(
        *(_citation(f"https://suzuki.test/page-{index}", f"Page {index}") for index in range(5))
    )
    server = FakeOpenRouter(script)

    results = run(openrouter_provider, server)

    assert [candidate.url for candidate in results.candidates] == [
        "https://suzuki.test/page-0",
        "https://suzuki.test/page-1",
        "https://bikez.test/gsr600",
    ]
    # The cap is reached before the third query, so that credit is not spent.
    assert server.queries == [PRODUCT_QUERY, TECHNICAL_QUERY]


def test_openrouter_a_missing_api_key_warns_and_makes_no_request(
    settings_override: Callable[..., None],
) -> None:
    settings_override(OPENROUTER_API_KEY="")

    def handle(request: httpx2.Request) -> httpx2.Response:  # pragma: no cover
        raise AssertionError("no request may be made without a key")

    async def call() -> search.SearchResults:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as client:
            return await search.OpenRouterSearchProvider().search(
                NAME, client=client, gate=RecordingGate()
            )

    results = asyncio.run(call())

    assert results.candidates == ()
    assert results.warnings == ("Web search skipped: OPENROUTER_API_KEY is not configured.",)


def test_openrouter_a_failed_query_warns_and_the_others_still_run(
    openrouter_provider: search.OpenRouterSearchProvider,
) -> None:
    server = FakeOpenRouter()
    server.status[TECHNICAL_QUERY] = 500

    results = run(openrouter_provider, server)

    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.PRODUCT,
        SourceType.PRODUCT,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert len(results.warnings) == 1
    assert TECHNICAL_QUERY in results.warnings[0]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="no-choices"),
        pytest.param({"choices": []}, id="empty-choices"),
        pytest.param(
            {"choices": [{"message": {"content": "no annotations"}}]}, id="no-annotations"
        ),
        pytest.param({"choices": ["not-a-mapping"]}, id="choice-not-a-mapping"),
        pytest.param(
            {
                "choices": [
                    {"message": {"annotations": [{"type": "file"}, {"type": "url_citation"}]}}
                ]
            },
            id="no-url-citation",
        ),
        pytest.param(
            {
                "choices": [
                    {"message": {"annotations": [{"type": "url_citation", "url_citation": 7}]}}
                ]
            },
            id="citation-not-a-mapping",
        ),
        pytest.param(
            {
                "choices": [
                    {
                        "message": {
                            "annotations": [
                                {"type": "url_citation", "url_citation": {"url": None}},
                                {"type": "url_citation", "url_citation": {"url": "  "}},
                            ]
                        }
                    }
                ]
            },
            id="unusable-url",
        ),
    ],
)
def test_openrouter_skips_malformed_payloads_without_raising(
    openrouter_provider: search.OpenRouterSearchProvider,
    payload: Any,
) -> None:
    script = _default_openrouter_script()
    script[PRODUCT_QUERY] = payload
    server = FakeOpenRouter(script)

    results = run(openrouter_provider, server)

    assert [candidate.source_type for candidate in results.candidates] == [
        SourceType.TECHNICAL,
        SourceType.TECHNICAL,
        SourceType.MAGAZINE,
        SourceType.MAGAZINE,
    ]
    assert results.warnings == ()


def test_openrouter_falls_back_to_the_url_as_title(
    openrouter_provider: search.OpenRouterSearchProvider,
) -> None:
    script = _default_openrouter_script()
    script[PRODUCT_QUERY] = _completion(
        {"url": "https://suzuki.test/untitled?utm_source=openai"},
        {"url": "https://suzuki.test/blank", "title": "   "},
    )
    server = FakeOpenRouter(script)

    results = run(openrouter_provider, server)

    assert [(c.url, c.title) for c in results.candidates[:2]] == [
        ("https://suzuki.test/untitled", "https://suzuki.test/untitled"),
        ("https://suzuki.test/blank", "https://suzuki.test/blank"),
    ]


def test_openrouter_every_query_passes_through_the_politeness_gate(
    openrouter_provider: search.OpenRouterSearchProvider,
) -> None:
    gate = RecordingGate()

    run(openrouter_provider, FakeOpenRouter(), gate=gate)

    assert gate.hosts == ["openrouter.ai"] * 3


def test_get_search_provider_returns_openrouter_when_configured(
    settings_override: Callable[..., None],
) -> None:
    settings_override(SEARCH_PROVIDER="openrouter")

    provider = search.get_search_provider()

    assert isinstance(provider, search.OpenRouterSearchProvider)
    assert provider.name == "openrouter"


def test_pinned_call_shape_and_templates_match_the_phase_contract() -> None:
    assert search.TAVILY_SEARCH_URL == "https://api.tavily.com/search"
    assert search.TAVILY_SEARCH_DEPTH == "basic"
    assert search.RESULTS_PER_TEMPLATE == 2
    assert [(template.source_type, template.template) for template in search.QUERY_TEMPLATES] == [
        (SourceType.PRODUCT, '"{name}" motorcycle official specifications'),
        (SourceType.TECHNICAL, '"{name}" technical data specifications'),
        (SourceType.MAGAZINE, '"{name}" review test'),
    ]


# --- the `templates` keyword (step 6.17) ----------------------------------------


def test_tavily_defaults_to_the_pinned_templates(
    provider: search.TavilySearchProvider,
) -> None:
    """Omitting `templates` is byte-identical to today: the module constant runs."""
    server = FakeTavily()

    results = run(provider, server)

    assert server.queries == [PRODUCT_QUERY, TECHNICAL_QUERY, MAGAZINE_QUERY]
    assert len(results.candidates) == 6


def test_tavily_runs_the_templates_it_is_given_instead_of_the_module_constant(
    provider: search.TavilySearchProvider,
    settings_override: Callable[..., None],
) -> None:
    # The default cap (6) is exactly filled by the three pinned templates'
    # two results each, so the extra (4th) template never gets to run unless
    # the cap is raised — a fact about the cap, not about `templates`.
    settings_override(INGESTION_MAX_WEB_DOCUMENTS=8)
    extra_query = f'"{NAME}" K80 K81 motorcycle specifications'
    templates = (
        *search.QUERY_TEMPLATES,
        search.QueryTemplate(SourceType.TECHNICAL, '"{name}" K80 K81 motorcycle specifications'),
    )
    script = _default_script()
    script[extra_query] = [_result("https://oem.test/k80", "Type K80 data sheet")]
    server = FakeTavily(script)

    results = run(provider, server, templates=templates)

    assert server.queries == [PRODUCT_QUERY, TECHNICAL_QUERY, MAGAZINE_QUERY, extra_query]
    assert results.candidates[-1].url == "https://oem.test/k80"


def test_openrouter_runs_the_templates_it_is_given_instead_of_the_module_constant(
    openrouter_provider: search.OpenRouterSearchProvider,
    settings_override: Callable[..., None],
) -> None:
    settings_override(INGESTION_MAX_WEB_DOCUMENTS=8)
    extra_query = f'"{NAME}" K80 K81 motorcycle specifications'
    templates = (
        *search.QUERY_TEMPLATES,
        search.QueryTemplate(SourceType.TECHNICAL, '"{name}" K80 K81 motorcycle specifications'),
    )
    script = _default_openrouter_script()
    script[extra_query] = _completion(_citation("https://oem.test/k80", "Type K80 data sheet"))
    server = FakeOpenRouter(script)

    results = run(openrouter_provider, server, templates=templates)

    assert server.queries == [PRODUCT_QUERY, TECHNICAL_QUERY, MAGAZINE_QUERY, extra_query]
    assert results.candidates[-1].url == "https://oem.test/k80"


def test_strip_utm_source_is_the_public_alias_of_the_openrouter_cleaner() -> None:
    tagged = "https://de.wikipedia.org/wiki/BMW_F_750_GS?utm_source=chatgpt.com"
    assert search.strip_utm_source(tagged) == "https://de.wikipedia.org/wiki/BMW_F_750_GS"
    # Every other query parameter is kept verbatim.
    kept = "https://example.test/page?utm_source=chatgpt.com&lang=de"
    assert search.strip_utm_source(kept) == "https://example.test/page?lang=de"
