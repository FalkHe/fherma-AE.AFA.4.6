"""Tests for `app.services.ingestion.extract`.

The saved fixtures stand in for the cases that matter downstream: an article
whose headings must survive into the Markdown (step 2.18 chunks on them), the
same in Wikipedia's REST HTML shape — bare `<section>` elements under `<body>`
and no article container, which is what made trafilatura drop every heading —
and a page with no main text at all, which must come back as a typed failure.
"""

from collections.abc import Callable

from app.services.ingestion import extract


def test_extracts_headings_prose_and_tables(html_fixture: Callable[[str], str]) -> None:
    outcome = extract.extract_markdown(html_fixture("gsr600_article.html"), url="https://x.test/a")

    assert isinstance(outcome, extract.ExtractResult)
    markdown = outcome.markdown
    assert markdown.startswith("# Suzuki GSR600")
    assert "## Design" in markdown
    assert "### Chassis and brakes" in markdown
    assert "| Displacement | 599 cm³ |" in markdown
    assert "detuned version of the GSX-R600" in markdown


def test_drops_navigation_and_footer_boilerplate(html_fixture: Callable[[str], str]) -> None:
    outcome = extract.extract_markdown(html_fixture("gsr600_article.html"))

    assert isinstance(outcome, extract.ExtractResult)
    assert "Random article" not in outcome.markdown
    assert "Privacy policy" not in outcome.markdown
    assert "Accept all cookies" not in outcome.markdown


def test_keeps_headings_of_wikipedia_rest_html(html_fixture: Callable[[str], str]) -> None:
    """The REST HTML shape our main source serves must chunk with a heading path.

    Its sections are bare `<section>` elements under `<body>`, so trafilatura's
    main-body detection finds no article container and its recovery pass keeps
    the prose but no heading. The rescue pass in `extract_markdown` is what puts
    the `##`/`###` lines back.
    """
    outcome = extract.extract_markdown(
        html_fixture("wikipedia_rest_gsr600.html"),
        url="https://en.wikipedia.org/api/rest_v1/page/html/Suzuki_GSR600",
    )

    assert isinstance(outcome, extract.ExtractResult)
    markdown = outcome.markdown
    assert "## Design" in markdown
    assert "### Chassis and brakes" in markdown
    assert "### Engine" in markdown
    assert "## Reception" in markdown
    # A GFM table (the infobox) and the lead prose survive alongside them.
    assert "| Displacement | 599 cm³ |" in markdown
    assert "detuned version of the GSX-R600" in markdown


def test_keeps_wikipedia_rest_headings_above_their_own_section(
    html_fixture: Callable[[str], str],
) -> None:
    """Heading levels and positions must match the source, not just be present."""
    outcome = extract.extract_markdown(html_fixture("wikipedia_rest_gsr600.html"))

    assert isinstance(outcome, extract.ExtractResult)
    markdown = outcome.markdown
    assert markdown.index("## Design") < markdown.index("### Chassis and brakes")
    assert (
        markdown.index("### Chassis and brakes")
        < markdown.index("Twin 290 mm front discs")
        < markdown.index("### Engine")
    )
    assert markdown.index("### Engine") < markdown.index("## Reception")


def test_rescued_headings_do_not_bring_boilerplate_back(
    html_fixture: Callable[[str], str],
) -> None:
    """The rescue pass must not buy headings with navigation and footer text."""
    outcome = extract.extract_markdown(html_fixture("sectioned_review.html"))

    assert isinstance(outcome, extract.ExtractResult)
    markdown = outcome.markdown
    assert "## Riding impressions" in markdown
    assert "### What we would change" in markdown
    assert "Random article" not in markdown
    assert "Accept all cookies" not in markdown
    assert "Privacy policy" not in markdown


def test_normalizes_whitespace(html_fixture: Callable[[str], str]) -> None:
    outcome = extract.extract_markdown(html_fixture("gsr600_article.html"))

    assert isinstance(outcome, extract.ExtractResult)
    markdown = outcome.markdown
    assert "\n\n\n" not in markdown
    assert "\u00a0" not in markdown
    assert markdown == markdown.strip()
    assert not any(line != line.rstrip() for line in markdown.splitlines())


def test_reports_an_empty_extraction_as_a_typed_failure(
    html_fixture: Callable[[str], str],
) -> None:
    outcome = extract.extract_markdown(
        html_fixture("no_main_text.html"), url="https://x.test/login"
    )

    assert isinstance(outcome, extract.ExtractFailure)
    assert outcome.reason is extract.ExtractFailureReason.EMPTY
    assert "https://x.test/login" in outcome.detail


def test_reports_unparseable_input_as_a_typed_failure() -> None:
    assert isinstance(extract.extract_markdown(""), extract.ExtractFailure)
    assert isinstance(extract.extract_markdown("neither html nor text"), extract.ExtractFailure)


def test_keeps_the_first_pass_text_for_a_page_without_any_heading() -> None:
    """A heading-less page is normal, not a failure: the prose is still returned."""
    prose = (
        "The GSR600 was sold in Europe between 2006 and 2011 as the naked "
        "middleweight of the GSX-R600 family, and it kept the same steel tube "
        "frame throughout its production run without a single model year change."
    )
    outcome = extract.extract_markdown(f"<html><body><div><p>{prose}</p></div></body></html>")

    assert isinstance(outcome, extract.ExtractResult)
    assert prose in outcome.markdown
    assert "#" not in outcome.markdown


def test_normalize_treats_nothing_extracted_as_empty() -> None:
    assert extract.normalize(None) == ""


def test_normalize_collapses_blank_lines_and_trailing_space() -> None:
    assert extract.normalize("# A  \r\n\r\n\r\n\r\ntext here \n") == "# A\n\ntext here"
