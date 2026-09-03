"""Wikipedia as the first, most trustworthy source for one motorbike.

The adapter is four pinned HTTP calls behind three composable steps:

1. `find_page` — REST search (`rest.php/v1/search/page`, limit 3) picks the best
   hit and **records the title it matched**. That recorded title becomes
   `source_documents.source_title`, which is the disambiguation guard: an admin
   reviewing "Suzuki GSR 600" sees whether we brought back the GSR600 article or
   something adjacent.
2. `fetch_article` — the page HTML (`api/rest_v1/page/html/{key}`) through the
   shared fetch layer, then the shared extraction, so Wikipedia obeys exactly
   the same limits and produces exactly the same Markdown shape as any other
   source.
3. `find_image` — the lead image URL (`api/rest_v1/page/summary/{key}`) plus the
   two-call attribution chain, because the summary carries no licence data: the
   file title comes from the action API (`prop=pageimages&piprop=name`), the
   licence and author from Commons (`prop=imageinfo&iiprop=extmetadata`).

`lookup` runs all three for the ingestion job. Like the rest of the ingestion
layer, an expected outcome — no matching article, an unreachable API, an
unextractable page — is a **returned** typed failure, never an exception: only
the job knows whether a missing source is a warning or the end of the run. A
missing image or missing licence metadata is weaker still: the article survives
it, so it is simply `None`.
"""

import html
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import quote, urlsplit

import httpx2

from app.services.ingestion import extract, fetch

logger = logging.getLogger(__name__)

WIKIPEDIA_ORIGIN = "https://en.wikipedia.org"
COMMONS_ORIGIN = "https://commons.wikimedia.org"

# The four pinned endpoints (live-verified for the Phase-2 contract).
SEARCH_URL = f"{WIKIPEDIA_ORIGIN}/w/rest.php/v1/search/page"
ARTICLE_URL_TEMPLATE = f"{WIKIPEDIA_ORIGIN}/api/rest_v1/page/html/{{key}}"
SUMMARY_URL_TEMPLATE = f"{WIKIPEDIA_ORIGIN}/api/rest_v1/page/summary/{{key}}"
ACTION_API_URL = f"{WIKIPEDIA_ORIGIN}/w/api.php"
COMMONS_API_URL = f"{COMMONS_ORIGIN}/w/api.php"

# The human-readable article URL — what provenance stores and the admin clicks,
# never the REST endpoint we actually fetched.
PAGE_URL_TEMPLATE = f"{WIKIPEDIA_ORIGIN}/wiki/{{key}}"

# How many hits the search asks for. We use the first usable one; the rest exist
# so a future step could offer the admin alternatives.
SEARCH_LIMIT = 3

# Only these extmetadata members are requested (pinned). `Credit` and
# `UsageTerms` are part of the pinned filter but deliberately not part of the
# composed attribution string.
EXTMETADATA_FILTER = "LicenseShortName|Artist|Credit|UsageTerms|LicenseUrl"

# Attribution is composed as "{Artist} · {LicenseShortName} · {LicenseUrl}".
ATTRIBUTION_SEPARATOR = " · "

# Commons delivers `Artist`/`Credit` as HTML fragments.
_HTML_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


class WikipediaFailureReason(StrEnum):
    """Why a lookup produced no usable article. Callers branch on this."""

    NO_MATCH = "no_match"
    """No Wikipedia article matched the name — deterministic, do not retry."""

    SEARCH_FAILED = "search_failed"
    ARTICLE_FETCH_FAILED = "article_fetch_failed"
    EXTRACTION_FAILED = "extraction_failed"


@dataclass(frozen=True, slots=True)
class WikipediaPage:
    """The article a name was resolved to, before anything was fetched."""

    key: str
    """Page key used in the REST calls, e.g. `Suzuki_GSR600`."""

    title: str
    """The title that matched — stored as `source_documents.source_title`."""

    url: str
    """Human-readable article URL — stored as `source_documents.source_url`."""


@dataclass(frozen=True, slots=True)
class WikipediaImage:
    """The article's lead image and the credit line to display with it."""

    url: str
    attribution: str | None
    """`"{Artist} · {LicenseShortName} · {LicenseUrl}"`, `None` when unknown."""


@dataclass(frozen=True, slots=True)
class WikipediaArticle:
    """A fetched article: the payload to retain and the text to store."""

    content: bytes
    """The raw fetched bytes, for `storage.save_raw_document`."""

    markdown: str


@dataclass(frozen=True, slots=True)
class WikipediaResult:
    """Everything one Wikipedia lookup yields for the ingestion job."""

    page: WikipediaPage
    content: bytes
    markdown: str
    image: WikipediaImage | None


@dataclass(frozen=True, slots=True)
class WikipediaFailure:
    """A lookup that produced no usable article, with a warning-ready `detail`."""

    reason: WikipediaFailureReason
    detail: str


WikipediaOutcome = WikipediaResult | WikipediaFailure


async def lookup(
    name: str,
    *,
    client: httpx2.AsyncClient | None = None,
    gate: fetch.PolitenessGate | None = None,
) -> WikipediaOutcome:
    """Resolve `name` to an article and bring back its text and lead image.

    Args:
        name: Display name as the admin entered it ("Suzuki GSR 600").
        client: Reuse an existing client (see `fetch.build_client`); when
            omitted, one is created and closed around the whole lookup.
        gate: Politeness gate to honour; defaults to the process-wide one.
    """
    if client is None:
        async with fetch.build_client() as owned_client:
            return await lookup(name, client=owned_client, gate=gate)

    page = await find_page(name, client=client, gate=gate)
    if isinstance(page, WikipediaFailure):
        return page

    article = await fetch_article(page, client=client, gate=gate)
    if isinstance(article, WikipediaFailure):
        return article

    return WikipediaResult(
        page=page,
        content=article.content,
        markdown=article.markdown,
        image=await find_image(page, client=client, gate=gate),
    )


async def find_page(
    name: str,
    *,
    client: httpx2.AsyncClient | None = None,
    gate: fetch.PolitenessGate | None = None,
) -> WikipediaPage | WikipediaFailure:
    """Search Wikipedia for `name` and return the best hit, title included."""
    payload = await _get_json(
        SEARCH_URL,
        params={"q": name, "limit": SEARCH_LIMIT},
        client=client,
        gate=gate,
    )
    if payload is None:
        return _report(
            WikipediaFailure(
                reason=WikipediaFailureReason.SEARCH_FAILED,
                detail=f"Wikipedia search for {name!r} failed.",
            )
        )

    page = _best_hit(payload)
    if page is None:
        return _report(
            WikipediaFailure(
                reason=WikipediaFailureReason.NO_MATCH,
                detail=f"No Wikipedia article matched {name!r}.",
            )
        )

    logger.info("Wikipedia matched %r to %r (%s).", name, page.title, page.key)
    return page


async def fetch_article(
    page: WikipediaPage,
    *,
    client: httpx2.AsyncClient | None = None,
    gate: fetch.PolitenessGate | None = None,
) -> WikipediaArticle | WikipediaFailure:
    """Fetch one article's HTML and extract it to normalized Markdown."""
    outcome = await fetch.fetch_html(
        ARTICLE_URL_TEMPLATE.format(key=_quote(page.key)),
        client=client,
        gate=gate,
    )
    if isinstance(outcome, fetch.FetchFailure):
        return _report(
            WikipediaFailure(
                reason=WikipediaFailureReason.ARTICLE_FETCH_FAILED,
                detail=f"Could not fetch the Wikipedia article {page.title!r}: {outcome.detail}",
            )
        )

    extracted = extract.extract_markdown(outcome.text, url=page.url)
    if isinstance(extracted, extract.ExtractFailure):
        return _report(
            WikipediaFailure(
                reason=WikipediaFailureReason.EXTRACTION_FAILED,
                detail=f"No text extracted from the Wikipedia article {page.title!r}.",
            )
        )

    return WikipediaArticle(content=outcome.content, markdown=extracted.markdown)


async def find_image(
    page: WikipediaPage,
    *,
    client: httpx2.AsyncClient | None = None,
    gate: fetch.PolitenessGate | None = None,
) -> WikipediaImage | None:
    """Return the article's lead image with its attribution, if it has one.

    An article without a lead image, an unreachable summary endpoint and missing
    licence metadata are all normal: the caller gets `None` (no image) or an
    image with `attribution=None` (the review UI renders its "unknown
    attribution" fallback and the admin judges the image).
    """
    summary = await _get_json(
        SUMMARY_URL_TEMPLATE.format(key=_quote(page.key)),
        params=None,
        client=client,
        gate=gate,
    )
    image_url = _original_image_url(summary)
    if image_url is None:
        logger.info("Wikipedia article %r has no lead image.", page.title)
        return None

    return WikipediaImage(
        url=image_url,
        attribution=await _find_attribution(page, client=client, gate=gate),
    )


def compose_attribution(metadata: Mapping[str, Any]) -> str | None:
    """Compose the stored credit line from Commons `extmetadata`.

    `"{Artist} · {LicenseShortName} · {LicenseUrl}"`; any missing piece is
    omitted, and when every piece is missing the result is `None` rather than a
    string of separators.
    """
    artist = strip_html(_metadata_value(metadata, "Artist"))
    licence_name = _plain_text(_metadata_value(metadata, "LicenseShortName"))
    licence_url = _plain_text(_metadata_value(metadata, "LicenseUrl"))

    parts = [part for part in (artist, licence_name, licence_url) if part]
    if not parts:
        return None
    return ATTRIBUTION_SEPARATOR.join(parts)


def strip_html(value: str | None) -> str | None:
    """Reduce an HTML metadata fragment to plain text (`None` when empty).

    Tags become spaces rather than nothing, so `<div>Name</div><div>Studio</div>`
    does not collapse into one word.
    """
    if not value:
        return None
    return _plain_text(html.unescape(_HTML_TAG.sub(" ", value)))


async def _find_attribution(
    page: WikipediaPage,
    *,
    client: httpx2.AsyncClient | None,
    gate: fetch.PolitenessGate | None,
) -> str | None:
    """Run the two-call chain: page image file title, then Commons metadata."""
    file_title = await _find_file_title(page, client=client, gate=gate)
    if file_title is None:
        logger.info("No page image file title for %r; attribution stays unknown.", page.title)
        return None

    metadata = await _find_extmetadata(file_title, client=client, gate=gate)
    if metadata is None:
        logger.info("No Commons metadata for %s; attribution stays unknown.", file_title)
        return None

    return compose_attribution(metadata)


async def _find_file_title(
    page: WikipediaPage,
    *,
    client: httpx2.AsyncClient | None,
    gate: fetch.PolitenessGate | None,
) -> str | None:
    """Return the `File:…` title of the article's page image, if it has one."""
    payload = await _get_json(
        ACTION_API_URL,
        params={
            "action": "query",
            "titles": page.key,
            "prop": "pageimages",
            "piprop": "name",
            "format": "json",
            "formatversion": 2,
        },
        client=client,
        gate=gate,
    )
    name = _plain_text(_first_page_member(payload, "pageimage"))
    return f"File:{name}" if name else None


async def _find_extmetadata(
    file_title: str,
    *,
    client: httpx2.AsyncClient | None,
    gate: fetch.PolitenessGate | None,
) -> Mapping[str, Any] | None:
    """Return the Commons `extmetadata` of one file, restricted to the filter."""
    payload = await _get_json(
        COMMONS_API_URL,
        params={
            "action": "query",
            "titles": file_title,
            "prop": "imageinfo",
            "iiprop": "extmetadata",
            "iiextmetadatafilter": EXTMETADATA_FILTER,
            "format": "json",
            "formatversion": 2,
        },
        client=client,
        gate=gate,
    )
    imageinfo = _first_page_member(payload, "imageinfo")
    if not isinstance(imageinfo, list) or not imageinfo:
        return None

    first = imageinfo[0]
    metadata = first.get("extmetadata") if isinstance(first, dict) else None
    return metadata if isinstance(metadata, dict) else None


async def _get_json(
    url: str,
    *,
    params: Mapping[str, Any] | None,
    client: httpx2.AsyncClient | None,
    gate: fetch.PolitenessGate | None,
) -> Any | None:
    """GET one JSON API response, or `None` with one logged warning.

    `fetch.fetch_html` cannot serve these calls (it accepts `text/html` only),
    so this is the JSON counterpart: same politeness gate, same client — and
    therefore the same pinned User-Agent — minus the size cap and the HTML
    content-type check.
    """
    if client is None:
        async with fetch.build_client() as owned_client:
            return await _get_json(url, params=params, client=owned_client, gate=gate)

    await (gate or fetch.politeness).wait((urlsplit(url).hostname or "").lower())

    try:
        response = await client.get(url, params=dict(params) if params else None)
    except httpx2.TimeoutException:
        logger.warning("Wikipedia API timed out: %s.", url)
        return None
    except httpx2.HTTPError as error:
        logger.warning("Wikipedia API unreachable: %s (%s).", url, type(error).__name__)
        return None

    if response.status_code >= 400:
        logger.warning("Wikipedia API answered HTTP %d for %s.", response.status_code, url)
        return None

    try:
        return response.json()
    except ValueError:
        logger.warning("Wikipedia API returned no usable JSON: %s.", url)
        return None


def _best_hit(payload: Any) -> WikipediaPage | None:
    """Pick the first search hit we can address; Wikipedia returns them ranked."""
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list):
        return None

    for hit in pages:
        if not isinstance(hit, dict):
            continue
        key = _plain_text(hit.get("key"))
        if not key:
            continue
        # `matched_title` is set when the hit was reached through a redirect and
        # is exactly what the admin should see; otherwise the title matched.
        title = _plain_text(hit.get("matched_title")) or _plain_text(hit.get("title")) or key
        return WikipediaPage(key=key, title=title, url=PAGE_URL_TEMPLATE.format(key=_quote(key)))

    return None


def _original_image_url(summary: Any) -> str | None:
    """Read `originalimage.source` out of a page summary."""
    original = summary.get("originalimage") if isinstance(summary, dict) else None
    source = original.get("source") if isinstance(original, dict) else None
    return _plain_text(source)


def _first_page_member(payload: Any, member: str) -> Any | None:
    """Read `query.pages[0].<member>` out of an action-API response."""
    query = payload.get("query") if isinstance(payload, dict) else None
    pages = query.get("pages") if isinstance(query, dict) else None
    if not isinstance(pages, list) or not pages:
        return None
    first = pages[0]
    return first.get(member) if isinstance(first, dict) else None


def _metadata_value(metadata: Mapping[str, Any], key: str) -> str | None:
    """Read one `extmetadata` entry's `value`, which is where the text lives."""
    entry = metadata.get(key)
    value = entry.get("value") if isinstance(entry, Mapping) else None
    return value if isinstance(value, str) else None


def _plain_text(value: Any) -> str | None:
    """Collapse whitespace in a string value; anything else is no value."""
    if not isinstance(value, str):
        return None
    return _WHITESPACE.sub(" ", value).strip() or None


def _quote(key: str) -> str:
    """Percent-encode a page key for a path segment (titles may contain `/`)."""
    return quote(key, safe="")


def _report(failure: WikipediaFailure) -> WikipediaFailure:
    """Log one structured warning and hand the failure back to the caller."""
    logger.warning("Wikipedia lookup failed (%s): %s", failure.reason.value, failure.detail)
    return failure
