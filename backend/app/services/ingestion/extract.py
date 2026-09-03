"""Turning fetched HTML into the normalized Markdown the pipeline stores.

trafilatura does the hard part (dropping navigation, footers, cookie banners and
comment sections). This module pins the options it is called with and normalizes
its output, because two later steps depend on the exact shape: 2.18 chunks on
Markdown headings, and 2.17 feeds the same text to the extraction prompt.

An article we cannot extract any main text from is a **returned** failure, not
an exception: for the ingestion job it is one lost source among several, and the
job decides what that means.

**Headings need a rescue pass.** trafilatura only keeps `<h1>`–`<h6>` when its
main-body detection recognises an article container in the document. Wikipedia's
REST HTML (`/api/rest_v1/page/html/{key}`, our main source) has none — its
content sits in bare `<section>` elements directly under `<body>` — so
extraction falls back to trafilatura's "wild text" recovery, which collects
paragraphs and tables and silently drops every heading. The prose survives, the
structure does not, and chunk `heading_path` comes out NULL for the whole
corpus. `_extract_with_article_container` therefore re-runs the extraction on a
copy of the document whose body is wrapped in one `<article>` element, and that
result is used when it really does carry headings without losing text.
"""

import logging
import re
from dataclasses import dataclass
from enum import StrEnum

import trafilatura

logger = logging.getLogger(__name__)

# Three or more consecutive newlines collapse to a paragraph break.
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")

# Trailing spaces (trafilatura leaves them on table rows) and NBSP-style spaces
# that would otherwise survive into chunks and prompts.
_TRAILING_SPACE = re.compile(r"[ \t]+$", re.MULTILINE)
_NON_BREAKING_SPACES = re.compile("[\u00a0\u2007\u202f]")

# An ATX heading line \u2014 what 2.18's chunker splits on, and the signal for
# whether the extraction kept the document's structure.
_ATX_HEADING = re.compile(r"^#{1,6} \S", re.MULTILINE)

# The container tag the rescue pass wraps a body in, chosen because it is one of
# the elements trafilatura's main-body detection looks for.
_ARTICLE_TAG = "article"


class ExtractFailureReason(StrEnum):
    """Why extraction produced no usable Markdown."""

    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class ExtractResult:
    """Extracted main text as normalized Markdown, headings preserved."""

    markdown: str


@dataclass(frozen=True, slots=True)
class ExtractFailure:
    """An extraction that produced nothing usable, with a warning-ready `detail`."""

    reason: ExtractFailureReason
    detail: str


ExtractOutcome = ExtractResult | ExtractFailure


def extract_markdown(html: str, *, url: str | None = None) -> ExtractOutcome:
    """Extract the main text of `html` as normalized Markdown.

    Headings survive: when the first pass returns none, the document is
    extracted a second time inside an `<article>` container (see the module
    docstring) and that result wins if it adds headings without dropping text.

    Args:
        html: The fetched document, decoded.
        url: The document's URL, used only for the log message when extraction
            comes back empty.
    """
    normalized = normalize(_extract(html))

    if not _ATX_HEADING.search(normalized):
        rescued = _extract_with_article_container(html)
        if _ATX_HEADING.search(rescued) and len(rescued) >= len(normalized):
            logger.debug(
                "Recovered %d heading(s) for %s with the article container pass.",
                len(_ATX_HEADING.findall(rescued)),
                url or "the document",
            )
            normalized = rescued

    if not normalized:
        detail = f"No main text extracted from {url}." if url else "No main text extracted."
        logger.warning("Extraction produced no text: %s", detail)
        return ExtractFailure(reason=ExtractFailureReason.EMPTY, detail=detail)

    return ExtractResult(markdown=normalized)


def normalize(markdown: str | None) -> str:
    """Normalize whitespace so chunking and prompting see one predictable shape.

    `None` — trafilatura's "nothing extracted" — normalizes to the empty string.
    """
    text = (markdown or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _NON_BREAKING_SPACES.sub(" ", text)
    text = _TRAILING_SPACE.sub("", text)
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def _extract(document: object) -> str | None:
    """Run trafilatura with the pinned options on HTML text or a parsed tree."""
    return trafilatura.extract(
        document,
        output_format="markdown",
        include_tables=True,
        include_comments=False,
        with_metadata=False,
    )


def _extract_with_article_container(html: str) -> str:
    """Extract `html` again with its whole body wrapped in one `<article>`.

    The wrapper is what gives trafilatura's main-body detection something to
    recognise in documents that carry no article container of their own (see the
    module docstring). Boilerplate removal is unaffected — trafilatura still
    prunes navigation, footers and asides inside the container — and a document
    that cannot be parsed at all simply yields no rescue.
    """
    tree = trafilatura.load_html(html)
    if tree is None:
        return ""

    body = tree if tree.tag == "body" else tree.find("body")
    if body is None:
        return ""

    article = body.makeelement(_ARTICLE_TAG, {})
    article.text, body.text = body.text, None
    for child in list(body):
        body.remove(child)
        article.append(child)
    body.append(article)

    return normalize(_extract(tree))
