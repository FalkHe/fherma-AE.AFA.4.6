"""Tests for `app.services.ingestion.wikipedia`.

Every one of the four pinned endpoints is answered by an `httpx2.MockTransport`
from recorded JSON in `fixtures/`, so the endpoint URLs, parameters and response
handling are provable without a network. `FakeWikipedia` is the recorded API: a
test that wants a different reality (no image, missing licence data, a 500)
mutates its payloads before the call.
"""

import asyncio
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from app.services.ingestion import fetch, wikipedia

NAME = "Suzuki GSR 600"
KEY = "Suzuki_GSR600"
TITLE = "Suzuki GSR600"
PAGE_URL = f"https://en.wikipedia.org/wiki/{KEY}"


class RecordingGate(fetch.PolitenessGate):
    """Politeness gate that records hosts instead of waiting for them."""

    def __init__(self) -> None:
        super().__init__(delay_seconds=0.0)
        self.hosts: list[str] = []

    async def wait(self, host: str) -> float:
        self.hosts.append(host)
        return 0.0


class FakeWikipedia:
    """The recorded Wikipedia/Commons API, plus a log of what was requested."""

    def __init__(
        self,
        json_fixture: Callable[[str], Any],
        html_fixture: Callable[[str], str],
    ) -> None:
        self.search: Any = json_fixture("wikipedia_search.json")
        self.summary: Any = json_fixture("wikipedia_summary.json")
        self.pageimages: Any = json_fixture("wikipedia_pageimages.json")
        self.imageinfo: Any = json_fixture("commons_imageinfo.json")
        self.article_html = html_fixture("gsr600_article.html")
        self.article_status = 200
        self.search_status = 200
        self.requests: list[httpx2.Request] = []

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        """Route one request to its recorded response."""
        self.requests.append(request)
        host, path = request.url.host, request.url.path

        if path == "/w/rest.php/v1/search/page":
            if self.search_status != 200:
                return httpx2.Response(self.search_status, json={"error": "boom"})
            return httpx2.Response(200, json=self.search)
        if path.startswith("/api/rest_v1/page/html/"):
            return httpx2.Response(
                self.article_status,
                headers={"content-type": 'text/html; charset=utf-8; profile="html/2.8.0"'},
                content=self.article_html.encode(),
            )
        if path.startswith("/api/rest_v1/page/summary/"):
            return httpx2.Response(200, json=self.summary)
        if host == "commons.wikimedia.org" and path == "/w/api.php":
            return httpx2.Response(200, json=self.imageinfo)
        if host == "en.wikipedia.org" and path == "/w/api.php":
            return httpx2.Response(200, json=self.pageimages)

        raise AssertionError(f"unexpected request: {request.url}")

    def request_for(self, path: str, *, host: str = "en.wikipedia.org") -> httpx2.Request:
        """Return the single request made to `path`, failing if there is none."""
        matches = [
            request
            for request in self.requests
            if request.url.host == host and request.url.path.startswith(path)
        ]
        assert len(matches) == 1, f"expected one request to {path}, got {len(matches)}"
        return matches[0]

    def extmetadata(self) -> dict[str, Any]:
        """The mutable `extmetadata` mapping of the recorded Commons response."""
        metadata = self.imageinfo["query"]["pages"][0]["imageinfo"][0]["extmetadata"]
        assert isinstance(metadata, dict)
        return metadata


@pytest.fixture
def server(
    json_fixture: Callable[[str], Any],
    html_fixture: Callable[[str], str],
) -> FakeWikipedia:
    """The recorded API every test in this module talks to."""
    return FakeWikipedia(json_fixture, html_fixture)


def run(
    server: FakeWikipedia,
    action: Callable[..., Any],
    gate: RecordingGate | None = None,
) -> Any:
    """Await `action(client=…, gate=…)` against the recorded API."""

    async def call() -> Any:
        async with httpx2.AsyncClient(
            transport=httpx2.MockTransport(server.handle),
            follow_redirects=True,
            headers={"User-Agent": fetch.USER_AGENT},
        ) as client:
            return await action(client=client, gate=gate or RecordingGate())

    return asyncio.run(call())


# --- search / matched title -------------------------------------------------


def test_lookup_returns_the_matched_page_the_payload_and_the_markdown(
    server: FakeWikipedia,
) -> None:
    outcome = run(server, lambda **kw: wikipedia.lookup(NAME, **kw))

    assert isinstance(outcome, wikipedia.WikipediaResult)
    assert (outcome.page.key, outcome.page.title, outcome.page.url) == (KEY, TITLE, PAGE_URL)
    assert outcome.content == server.article_html.encode()
    assert outcome.markdown.startswith("# Suzuki GSR600")
    assert "cookies" not in outcome.markdown


def test_search_uses_the_pinned_endpoint_query_and_limit(server: FakeWikipedia) -> None:
    run(server, lambda **kw: wikipedia.find_page(NAME, **kw))

    request = server.request_for("/w/rest.php/v1/search/page")
    assert request.url.params["q"] == NAME
    assert request.url.params["limit"] == str(wikipedia.SEARCH_LIMIT) == "3"


def test_records_the_matched_title_when_the_hit_came_from_a_redirect(
    server: FakeWikipedia,
) -> None:
    server.search["pages"][0]["matched_title"] = "GSR 600"

    page = run(server, lambda **kw: wikipedia.find_page(NAME, **kw))

    assert isinstance(page, wikipedia.WikipediaPage)
    # The admin must see what was matched, not only which article we landed on.
    assert page.title == "GSR 600"
    assert page.key == KEY


def test_picks_the_first_hit_that_can_be_addressed(server: FakeWikipedia) -> None:
    server.search["pages"][0].pop("key")

    page = run(server, lambda **kw: wikipedia.find_page(NAME, **kw))

    assert isinstance(page, wikipedia.WikipediaPage)
    assert (page.key, page.title) == ("Suzuki_GSX-R600", "Suzuki GSX-R600")


def test_reports_no_match_for_an_empty_result_list(server: FakeWikipedia) -> None:
    server.search["pages"] = []

    page = run(server, lambda **kw: wikipedia.find_page(NAME, **kw))

    assert isinstance(page, wikipedia.WikipediaFailure)
    assert page.reason is wikipedia.WikipediaFailureReason.NO_MATCH
    assert NAME in page.detail


def test_reports_a_failed_search_separately_from_no_match(server: FakeWikipedia) -> None:
    server.search_status = 500

    page = run(server, lambda **kw: wikipedia.find_page(NAME, **kw))

    assert isinstance(page, wikipedia.WikipediaFailure)
    assert page.reason is wikipedia.WikipediaFailureReason.SEARCH_FAILED


def test_lookup_stops_at_a_no_match_without_fetching_anything(server: FakeWikipedia) -> None:
    server.search["pages"] = []

    outcome = run(server, lambda **kw: wikipedia.lookup(NAME, **kw))

    assert isinstance(outcome, wikipedia.WikipediaFailure)
    assert [request.url.path for request in server.requests] == ["/w/rest.php/v1/search/page"]


# --- article ----------------------------------------------------------------


def test_article_is_fetched_from_the_pinned_rest_endpoint(server: FakeWikipedia) -> None:
    run(server, lambda **kw: wikipedia.lookup(NAME, **kw))

    request = server.request_for("/api/rest_v1/page/html/")
    assert request.url.path == f"/api/rest_v1/page/html/{KEY}"


def test_reports_an_unfetchable_article(server: FakeWikipedia) -> None:
    server.article_status = 404

    outcome = run(server, lambda **kw: wikipedia.lookup(NAME, **kw))

    assert isinstance(outcome, wikipedia.WikipediaFailure)
    assert outcome.reason is wikipedia.WikipediaFailureReason.ARTICLE_FETCH_FAILED


def test_reports_an_article_without_extractable_text(
    server: FakeWikipedia,
    html_fixture: Callable[[str], str],
) -> None:
    server.article_html = html_fixture("no_main_text.html")

    outcome = run(server, lambda **kw: wikipedia.lookup(NAME, **kw))

    assert isinstance(outcome, wikipedia.WikipediaFailure)
    assert outcome.reason is wikipedia.WikipediaFailureReason.EXTRACTION_FAILED


# --- image URL and attribution chain ----------------------------------------


def test_returns_the_original_image_with_a_composed_attribution(server: FakeWikipedia) -> None:
    outcome = run(server, lambda **kw: wikipedia.lookup(NAME, **kw))

    assert isinstance(outcome, wikipedia.WikipediaResult)
    assert outcome.image is not None
    assert (
        outcome.image.url == "https://upload.wikimedia.org/wikipedia/commons/1/12/Suzuki_GSR600.jpg"
    )
    # HTML stripped, entities decoded, pinned separator.
    assert outcome.image.attribution == (
        "Rider Dave · CC BY-SA 3.0 · https://creativecommons.org/licenses/by-sa/3.0"
    )


def test_attribution_chain_uses_the_pinned_endpoints_and_filter(server: FakeWikipedia) -> None:
    run(server, lambda **kw: wikipedia.find_image(_page(), **kw))

    file_title_request = server.request_for("/w/api.php")
    assert dict(file_title_request.url.params) == {
        "action": "query",
        "titles": KEY,
        "prop": "pageimages",
        "piprop": "name",
        "format": "json",
        "formatversion": "2",
    }

    commons_request = server.request_for("/w/api.php", host="commons.wikimedia.org")
    assert dict(commons_request.url.params) == {
        "action": "query",
        "titles": "File:Suzuki_GSR600.jpg",
        "prop": "imageinfo",
        "iiprop": "extmetadata",
        "iiextmetadatafilter": "LicenseShortName|Artist|Credit|UsageTerms|LicenseUrl",
        "format": "json",
        "formatversion": "2",
    }


def test_returns_no_image_when_the_summary_has_none(server: FakeWikipedia) -> None:
    server.summary.pop("originalimage")

    image = run(server, lambda **kw: wikipedia.find_image(_page(), **kw))

    assert image is None
    # No point asking Commons about a file that does not exist.
    assert not [request for request in server.requests if request.url.path == "/w/api.php"]


def test_keeps_the_image_when_the_file_title_is_missing(server: FakeWikipedia) -> None:
    server.pageimages["query"]["pages"][0].pop("pageimage")

    image = run(server, lambda **kw: wikipedia.find_image(_page(), **kw))

    assert isinstance(image, wikipedia.WikipediaImage)
    assert image.attribution is None
    assert not [
        request for request in server.requests if request.url.host == "commons.wikimedia.org"
    ]


def test_keeps_the_image_when_commons_has_no_metadata(server: FakeWikipedia) -> None:
    server.imageinfo["query"]["pages"][0].pop("imageinfo")

    image = run(server, lambda **kw: wikipedia.find_image(_page(), **kw))

    assert isinstance(image, wikipedia.WikipediaImage)
    assert image.attribution is None


def test_composes_only_the_pieces_commons_actually_returned(server: FakeWikipedia) -> None:
    metadata = server.extmetadata()
    metadata.pop("Artist")
    metadata.pop("LicenseUrl")

    image = run(server, lambda **kw: wikipedia.find_image(_page(), **kw))

    assert isinstance(image, wikipedia.WikipediaImage)
    assert image.attribution == "CC BY-SA 3.0"


def test_attribution_is_null_when_every_piece_is_missing(server: FakeWikipedia) -> None:
    metadata = server.extmetadata()
    for key in ("Artist", "LicenseShortName", "LicenseUrl"):
        metadata.pop(key)

    image = run(server, lambda **kw: wikipedia.find_image(_page(), **kw))

    assert isinstance(image, wikipedia.WikipediaImage)
    assert image.attribution is None


def test_compose_attribution_strips_html_and_collapses_whitespace() -> None:
    composed = wikipedia.compose_attribution(
        {
            "Artist": {"value": '<div>Jane\n Doe</div><div class="x">Studio &amp; Co</div>'},
            "LicenseShortName": {"value": "CC BY 4.0"},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by/4.0"},
        }
    )

    assert composed == (
        "Jane Doe Studio & Co · CC BY 4.0 · https://creativecommons.org/licenses/by/4.0"
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"Artist": {"value": ""}},
        {"Artist": {"value": "<span></span>"}},
        {"LicenseShortName": {"novalue": "CC0"}},
        {"Artist": "not a mapping"},
    ],
)
def test_compose_attribution_returns_none_without_usable_metadata(
    metadata: dict[str, Any],
) -> None:
    assert wikipedia.compose_attribution(metadata) is None


# --- manners ----------------------------------------------------------------


def test_every_call_passes_through_the_politeness_gate(server: FakeWikipedia) -> None:
    gate = RecordingGate()

    run(server, lambda **kw: wikipedia.lookup(NAME, **kw), gate=gate)

    assert gate.hosts == [
        "en.wikipedia.org",  # search
        "en.wikipedia.org",  # article HTML
        "en.wikipedia.org",  # summary
        "en.wikipedia.org",  # page image file title
        "commons.wikimedia.org",  # licence metadata
    ]


def test_a_json_endpoint_answering_html_is_treated_as_no_data(server: FakeWikipedia) -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=b"<html>not json</html>")

    async def call() -> Any:
        async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as client:
            return await wikipedia.find_page(NAME, client=client, gate=RecordingGate())

    page = asyncio.run(call())

    assert isinstance(page, wikipedia.WikipediaFailure)
    assert page.reason is wikipedia.WikipediaFailureReason.SEARCH_FAILED


def test_pinned_endpoints_match_the_phase_contract() -> None:
    assert wikipedia.SEARCH_URL == "https://en.wikipedia.org/w/rest.php/v1/search/page"
    assert wikipedia.ARTICLE_URL_TEMPLATE == "https://en.wikipedia.org/api/rest_v1/page/html/{key}"
    assert (
        wikipedia.SUMMARY_URL_TEMPLATE == "https://en.wikipedia.org/api/rest_v1/page/summary/{key}"
    )
    assert wikipedia.ACTION_API_URL == "https://en.wikipedia.org/w/api.php"
    assert wikipedia.COMMONS_API_URL == "https://commons.wikimedia.org/w/api.php"
    assert wikipedia.ATTRIBUTION_SEPARATOR == " · "


def test_a_title_with_a_slash_is_encoded_as_one_path_segment(server: FakeWikipedia) -> None:
    server.search["pages"][0]["key"] = "AC/DC"

    page = run(server, lambda **kw: wikipedia.find_page(NAME, **kw))
    assert isinstance(page, wikipedia.WikipediaPage)
    assert page.url == "https://en.wikipedia.org/wiki/AC%2FDC"

    run(server, lambda **kw: wikipedia.fetch_article(page, **kw))
    assert server.requests[-1].url.raw_path.decode().endswith("/page/html/AC%2FDC")


def _page() -> wikipedia.WikipediaPage:
    """The page a search would have produced, for the image-only tests."""
    return wikipedia.WikipediaPage(key=KEY, title=TITLE, url=PAGE_URL)
