"""`app suggestions` — bulk-add proposed models to the backlog.

A *suggestion* is a catalogue entry in `backlog` plus everything its source
claimed about it. Nothing here is treated as a fact: the claims land in the
`motorbikes.suggestion` JSON document, never in the typed columns, and no
ingestion is started. Research is what turns a suggestion into catalogue data,
and the admin starts it from the backlog screen ("Start ingestion").

- `app suggestions import` reads a model list (default:
  `backend/resources/bike-list.txt`) and creates one backlog entry per line,
  through `product_service.create_backlog` — the same path the admin UI and the
  advisor's `flag_unknown_bike` tool use. No LLM, no network.

The list format is the Markdown-ish shape the file is written in::

    BMW R 1200 GS (2004–2018) [K25/K50] ([Wikipedia][1])
    ...
    [1]: https://de.wikipedia.org/wiki/BMW_R_1200_GS_K25 "…"

so one line carries a name, one or more year ranges, the manufacturer's type
codes, and footnote references resolved against the definitions at the end of
the file. Everything but the name is optional.

The stored document has a fixed shape (keys always present)::

    {
      "source": "bike-list.txt",
      "raw": "BMW R 1200 GS (2004–2018) [K25/K50]",
      "manufacturer": "BMW",
      "model": "R 1200 GS",
      "year_from": 2004,
      "year_to": 2018,          # null when the range is open-ended
      "in_production": false,   # the range ended in "present"
      "year_ranges": [{"from": 2004, "to": 2018}],
      "type_codes": ["K25", "K50"],
      "links": ["https://de.wikipedia.org/wiki/BMW_R_1200_GS_K25"]
    }

An entry whose slug already exists is never re-created and never re-ingested
(the Phase-2b fresh-run pin): it only gains the suggestion document when it has
none yet, and is left untouched otherwise.

Follows the CLI async pattern of `app.cli.users`: the Typer command body stays
synchronous and calls `asyncio.run(...)`.
"""

import asyncio
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.motorbike import NAME_LENGTH
from app.db.session import get_sessionmaker
from app.services import product_service

app = typer.Typer(
    help="Add proposed models to the backlog, without starting ingestion.",
    no_args_is_help=True,
    add_completion=False,
)

# The curated list this command exists for; `backend/resources/bike-list.txt`
# relative to the backend root, which is this package's grandparent.
DEFAULT_LIST_PATH = Path(__file__).parents[2] / "resources" / "bike-list.txt"

# A footnote definition at the end of the file: `[1]: https://… "title"`.
_FOOTNOTE_DEFINITION = re.compile(r"^\[([^\]]+)\]:\s*(\S+)")
# A footnote reference inside an entry line: `([Wikipedia][1])`.
_FOOTNOTE_REFERENCE = re.compile(r"\(\[[^\]]*\]\[([^\]]+)\]\)")
# The trailing `[K25/K50]` bracket carrying manufacturer type codes.
_TYPE_CODES = re.compile(r"\[([^\]]+)\]\s*$")
# The trailing `(2004–2018, 2021–present)` bracket carrying the year ranges.
_YEAR_RANGES = re.compile(r"\(([^()]*\d{4}[^()]*)\)\s*$")
# One range inside it; the dash is an en dash in the file, a hyphen elsewhere.
_YEAR_RANGE = re.compile(r"(\d{4})\s*(?:[–—-]\s*(\d{4}|present|today|now))?", re.IGNORECASE)
# What "the model is still being built" is spelled as.
_OPEN_ENDED = frozenset({"present", "today", "now"})


@dataclass(frozen=True)
class ParsedModel:
    """One entry read from a model list: the name, and the claims about it."""

    name: str
    suggestion: dict[str, Any]


@dataclass(frozen=True)
class _ImportResult:
    """One line of the final summary table."""

    name: str
    outcome: str  # "added" | "enriched" | "skipped"
    detail: str = ""


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("import")
def import_list(
    path: Annotated[
        Path | None,
        typer.Argument(help="Model list to read; defaults to resources/bike-list.txt."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Parse and report, but write nothing."),
    ] = False,
) -> None:
    """Add every model in a list file to the backlog as a suggestion.

    Prints one line per model as it is processed, then a summary table. Nothing
    is ingested: the admin starts that per model from the backlog screen. Exits
    1 when the file yields no usable entry at all.
    """
    list_path = path or DEFAULT_LIST_PATH
    if not list_path.is_file():
        _fail(f"No model list at {list_path}.")

    models, warnings = parse_list(list_path.read_text(encoding="utf-8"), source=list_path.name)
    for warning in warnings:
        typer.echo(f"Warning: {warning}", err=True)
    if not models:
        _fail(f"{list_path} contains no model entries.")

    if dry_run:
        for model in models:
            typer.echo(f"{model.name}: would add ({_describe(model)})")
        typer.echo(f"\n{len(models)} model(s) parsed, nothing written.")
        return

    _print_summary(asyncio.run(_import(models)))


def parse_list(text: str, *, source: str) -> tuple[list[ParsedModel], list[str]]:
    """Parse a model list into entries plus one warning per unusable line.

    Blank lines and footnote definitions are structure, not entries, so they
    are silently consumed; a line that yields no slug-able name is reported and
    skipped, and so is a name the list repeats.
    """
    links = _footnote_definitions(text)
    models: list[ParsedModel] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for raw in text.splitlines():
        line = raw.strip()
        if not line or _FOOTNOTE_DEFINITION.match(line):
            continue

        model = _parse_entry(line, links=links, source=source)
        if model is None:
            warnings.append(f"Not a model entry, skipped: {line!r}")
            continue

        slug = product_service.slugify(model.name)
        if slug in seen:
            warnings.append(f"Duplicate in the list, skipped: {model.name!r}")
            continue
        seen.add(slug)
        models.append(model)

    return models, warnings


def _footnote_definitions(text: str) -> dict[str, str]:
    """Collect the `[ref]: url` definitions a line's references point at."""
    definitions: dict[str, str] = {}
    for line in text.splitlines():
        match = _FOOTNOTE_DEFINITION.match(line.strip())
        if match is not None:
            definitions[match.group(1)] = match.group(2)
    return definitions


def _parse_entry(line: str, *, links: dict[str, str], source: str) -> ParsedModel | None:
    """Split one entry line into a name and the claims trailing it.

    Returns `None` when nothing that could be a model name is left — which is
    how prose, headings and stray punctuation are rejected.
    """
    remainder, urls = _take_footnote_references(line, links)
    remainder, type_codes = _take_type_codes(remainder)
    remainder, ranges = _take_year_ranges(remainder)

    name = " ".join(remainder.split())[:NAME_LENGTH]
    if not product_service.slugify(name):
        return None

    manufacturer, _, model_name = name.partition(" ")
    years = [year for start, end in ranges for year in (start, end) if year is not None]
    in_production = any(end is None for _, end in ranges)
    return ParsedModel(
        name=name,
        suggestion={
            "source": source,
            "raw": line,
            "manufacturer": manufacturer,
            "model": model_name or None,
            "year_from": min(years) if years else None,
            "year_to": None if in_production or not years else max(years),
            "in_production": in_production,
            "year_ranges": [{"from": start, "to": end} for start, end in ranges],
            "type_codes": type_codes,
            "links": urls,
        },
    )


def _take_footnote_references(line: str, links: dict[str, str]) -> tuple[str, list[str]]:
    """Strip `([Wikipedia][1])` references off `line` and resolve their URLs.

    A reference without a definition contributes no link — the entry is still a
    perfectly good suggestion without it.
    """
    urls = [links[ref] for ref in _FOOTNOTE_REFERENCE.findall(line) if ref in links]
    return _FOOTNOTE_REFERENCE.sub("", line).strip(), urls


def _take_type_codes(line: str) -> tuple[str, list[str]]:
    """Strip a trailing `[K25/K50]` bracket off `line` and split its codes."""
    match = _TYPE_CODES.search(line)
    if match is None:
        return line, []
    codes = [code.strip() for code in match.group(1).split("/") if code.strip()]
    return line[: match.start()].strip(), codes


def _take_year_ranges(line: str) -> tuple[str, list[tuple[int, int | None]]]:
    """Strip a trailing `(2004–2018, 2021–present)` bracket and parse it.

    A range end of `None` means "still built"; a single year is a range of one,
    so `year_from`/`year_to` never have to special-case it.
    """
    match = _YEAR_RANGES.search(line)
    if match is None:
        return line, []

    ranges: list[tuple[int, int | None]] = []
    for start, end in _YEAR_RANGE.findall(match.group(1)):
        if not end:
            ranges.append((int(start), int(start)))
        elif end.lower() in _OPEN_ENDED:
            ranges.append((int(start), None))
        else:
            ranges.append((int(start), int(end)))
    return line[: match.start()].strip(), ranges


async def _import(models: list[ParsedModel]) -> list[_ImportResult]:
    """Async half of `import`: one session, every model, report-and-continue.

    No broker connection is opened, because nothing is enqueued.
    """
    async with get_sessionmaker()() as session:
        return [await _import_one(session, model) for model in models]


async def _import_one(session: AsyncSession, model: ParsedModel) -> _ImportResult:
    """Create one backlog entry, or attach the suggestion to the existing row."""
    existing = await product_service.get_by_slug(session, product_service.slugify(model.name))
    if existing is not None:
        if existing.suggestion is not None:
            typer.echo(f"{model.name}: skipped (exists: {existing.status.value})")
            return _ImportResult(model.name, "skipped", existing.status.value)
        await product_service.set_suggestion(session, existing, model.suggestion)
        typer.echo(f"{model.name}: enriched (exists: {existing.status.value})")
        return _ImportResult(model.name, "enriched", existing.status.value)

    await product_service.create_backlog(session, model.name, suggestion=model.suggestion)
    typer.echo(f"{model.name}: added ({_describe(model)})")
    return _ImportResult(model.name, "added")


def _describe(model: ParsedModel) -> str:
    """One-line summary of what a suggestion claims, for the progress lines."""
    suggestion = model.suggestion
    parts = [_year_range(suggestion)]
    if suggestion["type_codes"]:
        parts.append("/".join(suggestion["type_codes"]))
    if suggestion["links"]:
        parts.append(f"{len(suggestion['links'])} link(s)")
    return ", ".join(part for part in parts if part)


def _year_range(suggestion: dict[str, Any]) -> str:
    """Render the claimed year range the way `docs/model-naming.md` writes it."""
    if suggestion["year_from"] is None:
        return ""
    if suggestion["in_production"]:
        return f"from {suggestion['year_from']}"
    if suggestion["year_to"] == suggestion["year_from"]:
        return str(suggestion["year_from"])
    return f"{suggestion['year_from']}–{suggestion['year_to']}"


def _print_summary(results: list[_ImportResult]) -> None:
    """Print the final model -> outcome table, then a one-line totals count."""
    typer.echo("")
    typer.echo("Summary:")
    width = max((len(result.name) for result in results), default=0)
    for result in results:
        label = result.outcome
        if result.detail:
            label = f"{label} ({result.detail})"
        typer.echo(f"  {result.name:<{width}}  {label}")

    counts = Counter(result.outcome for result in results)
    typer.echo(
        f"{counts['added']} added, {counts['enriched']} enriched, {counts['skipped']} skipped."
    )
    typer.echo("Nothing was ingested — start ingestion per model from the admin backlog.")


def _fail(message: str) -> NoReturn:
    """Report why nothing was imported on stderr and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
