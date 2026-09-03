"""`app ingest` — drive the ingestion building blocks from a terminal.

Every command here is a manual smoke tool: they run the real integrations against
the real internet — the one thing the test suite deliberately never does.

- `app ingest fetch-url` (step 2.10) fetches and extracts one page and leaves the
  retained payload on disk so the storage layout can be inspected.
- `app ingest probe` (step 2.11) shows what ingestion *would* use for a model
  name: the Wikipedia article it matched (the disambiguation guard), its lead
  image, and the labelled search candidates.
- `app ingest fetch-image` (step 2.12) downloads one image for an existing
  catalogue entry and writes the variant set, so the `/media` mount and the
  pinned paths can be inspected against a real photo.
- `app ingest run` (step 2.14) is the real thing: it creates or finds the
  catalogue entry for a model name and enqueues its ingestion, exactly as
  `POST /api/products` does. The work happens in the worker, so this command
  prints the operation id and returns.
- `app ingest extract-specs` (step 2.17) re-runs the specification extraction
  for an already-ingested model and replaces its draft specification. It runs
  the LLM call **in this process** — nothing is enqueued, so the extracted
  fields are printed here, which is what makes it a prompt-tuning tool.

`fetch-image`, `run` and `extract-specs` touch the database; only `run` enqueues
a job.

Follows the CLI async pattern of `app.cli.users`: the Typer command body stays
synchronous and calls `asyncio.run(...)`.
"""

import asyncio
from typing import Annotated, NoReturn

import httpx2
import typer

from app.db.models.base import new_ulid
from app.db.models.motorbike_spec import SPEC_FIELDS
from app.db.session import get_sessionmaker
from app.jobs.broker import broker
from app.services import image_service, product_service, spec_extraction_service
from app.services.ingestion import extract, fetch, search, storage, wikipedia

app = typer.Typer(
    help="Run ingestion building blocks against a single source.",
    no_args_is_help=True,
    add_completion=False,
)

# Stand-in for the owning catalogue entry: this command has no motorbike row, so
# its payloads land in one clearly non-model directory instead of shadowing a
# real ULID.
CLI_MOTORBIKE_ID = "cli"


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("fetch-url")
def fetch_url(
    url: Annotated[str, typer.Argument(help="Absolute http(s) URL of an HTML page.")],
) -> None:
    """Fetch one page, retain the raw payload and print the extracted Markdown.

    Progress and provenance go to stderr, the Markdown to stdout, so the text
    can be piped straight into a file.
    """
    outcome = asyncio.run(fetch.fetch_html(url))
    if isinstance(outcome, fetch.FetchFailure):
        _fail(f"Fetch failed ({outcome.reason.value}): {outcome.detail}")

    raw_path = storage.save_raw_document(CLI_MOTORBIKE_ID, new_ulid(), outcome.content)
    typer.echo(
        f"Fetched {outcome.url} ({outcome.status_code}, {len(outcome.content)} bytes).",
        err=True,
    )
    typer.echo(f"Retained raw payload at {raw_path} (relative to DATA_DIR).", err=True)

    extracted = extract.extract_markdown(outcome.text, url=outcome.url)
    if isinstance(extracted, extract.ExtractFailure):
        _fail(f"Extraction failed ({extracted.reason.value}): {extracted.detail}")

    typer.echo(f"Extracted {len(extracted.markdown)} characters of Markdown.", err=True)
    typer.echo(extracted.markdown)


@app.command("probe")
def probe(
    name: Annotated[str, typer.Argument(help='Model name, e.g. "Suzuki GSR 600".')],
) -> None:
    """Show the sources ingestion would use for one model — nothing is stored.

    Prints the matched Wikipedia title and lead image plus every search
    candidate with the source type its query labelled it with. Warnings (a
    missing search key, a failed query) go to stderr.
    """
    asyncio.run(_probe(name))


async def _probe(name: str) -> None:
    """Run the Wikipedia lookup and the search provider on one shared client."""
    async with fetch.build_client() as client:
        await _probe_wikipedia(name, client)
        await _probe_search(name, client)


async def _probe_wikipedia(name: str, client: httpx2.AsyncClient) -> None:
    """Print the matched article and its lead image, or why there is neither."""
    page = await wikipedia.find_page(name, client=client)
    if isinstance(page, wikipedia.WikipediaFailure):
        typer.echo(f"Wikipedia:   no article ({page.reason.value}) — {page.detail}")
        return

    typer.echo(f"Wikipedia:   {page.title}")
    typer.echo(f"  URL:       {page.url}")
    typer.echo(f"  key:       {page.key}")

    image = await wikipedia.find_image(page, client=client)
    if image is None:
        typer.echo("  image:     none")
        return
    typer.echo(f"  image:     {image.url}")
    typer.echo(f"  credit:    {image.attribution or 'unknown attribution'}")


async def _probe_search(name: str, client: httpx2.AsyncClient) -> None:
    """Print the labelled search candidates and any warnings on stderr."""
    results = await search.get_search_provider().search(name, client=client)
    for warning in results.warnings:
        typer.echo(f"Warning: {warning}", err=True)

    if not results.candidates:
        typer.echo("Candidates:  none")
        return

    typer.echo(f"Candidates:  {len(results.candidates)}")
    for candidate in results.candidates:
        typer.echo(f"  [{candidate.source_type.value}] {candidate.title}")
        typer.echo(f"             {candidate.url}")


@app.command("fetch-image")
def fetch_image(
    url: Annotated[str, typer.Argument(help="Absolute http(s) URL of an image.")],
    motorbike_id: Annotated[
        str,
        typer.Argument(metavar="BIKE_ID", help="Id of an existing catalogue entry."),
    ],
    attribution: Annotated[
        str | None,
        typer.Option("--attribution", help="Credit line to store with the image."),
    ] = None,
) -> None:
    """Download one image for a catalogue entry and write its variant set.

    Creates the `pending` `motorbike_images` row and prints every path it wrote,
    relative to MEDIA_DIR — those are exactly the paths `/media` serves.
    """
    outcome = asyncio.run(_fetch_image(url, motorbike_id, attribution))
    if isinstance(outcome, image_service.ImageFailure):
        _fail(f"Image ingestion failed ({outcome.reason.value}): {outcome.detail}")

    typer.echo(f"Image {outcome.image.id} stored as {outcome.image.status.value}.", err=True)
    typer.echo(f"  original:  {outcome.original_path}")
    for variant, path in outcome.variant_paths.items():
        typer.echo(f"  {variant + ':':10} {path}")


async def _fetch_image(
    url: str, motorbike_id: str, attribution: str | None
) -> image_service.ImageOutcome:
    """Async half of `fetch-image`: one session, one service call.

    The catalogue entry is looked up first so an unknown id reports itself
    instead of surfacing as a foreign-key violation.
    """
    async with get_sessionmaker()() as session:
        motorbike = await product_service.get_motorbike(session, motorbike_id)
        if motorbike is None:
            _fail(f"No catalogue entry with id {motorbike_id!r}.")
        return await image_service.ingest_image(session, motorbike.id, url, attribution)


@app.command("run")
def run(
    name: Annotated[str, typer.Argument(help='Model name, e.g. "Suzuki GSR600".')],
) -> None:
    """Enqueue a full ingestion for one model, creating its entry if needed.

    The catalogue entry is looked up by its slug, so running this twice for the
    same name re-ingests the existing model instead of adding a second one.
    Nothing is waited for: the worker log and `GET /api/operations` are where
    the run is followed.
    """
    if not product_service.slugify(name):
        _fail(f"{name!r} contains no characters a slug can be built from.")

    try:
        motorbike_name, operation_id = asyncio.run(_run(name))
    except product_service.InvalidTransitionError as error:
        _fail(str(error))

    typer.echo(f"Enqueued ingestion of {motorbike_name!r} as operation {operation_id}.")


async def _run(name: str) -> tuple[str, str]:
    """Async half of `run`: create-or-find, then the pinned enqueue sequence.

    The broker connection is opened and closed around the enqueue, because a
    one-off CLI process owns the Redis connection it opens (same contract as
    `app jobs ping`).
    """
    await broker.startup()
    try:
        async with get_sessionmaker()() as session:
            motorbike = await product_service.get_by_slug(session, product_service.slugify(name))
            if motorbike is None:
                motorbike = await product_service.create_backlog(session, name)
                typer.echo(f"Created catalogue entry {motorbike.id}.", err=True)
            operation = await product_service.start_ingestion(session, motorbike)
            return motorbike.query_name, operation.id
    finally:
        await broker.shutdown()


@app.command("extract-specs")
def extract_specs(
    slug: Annotated[
        str,
        typer.Argument(help='Slug of an existing catalogue entry, e.g. "suzuki-gsr600".'),
    ],
    model: Annotated[
        str | None,
        typer.Option(help="OpenRouter model id; defaults to CHAT_MODEL."),
    ] = None,
) -> None:
    """Extract the draft specification of one model from its stored documents.

    Runs the LLM call in this process (nothing is enqueued) and replaces the
    `draft` specification — the `verified` one is never touched. Running it
    twice leaves exactly one draft row, so this is the prompt-tuning loop:
    change `spec_extraction.md`, run again, read the fields.
    """
    outcome = asyncio.run(_extract_specs(slug, model))
    if isinstance(outcome, spec_extraction_service.ExtractionFailure):
        _fail(f"Extraction failed ({outcome.reason.value}): {outcome.detail}")

    typer.echo(
        f"Extracted {len(outcome.extracted.filled_fields())} field(s) "
        f"from {outcome.documents} document(s) into draft {outcome.spec.id}.",
        err=True,
    )
    for field in SPEC_FIELDS:
        typer.echo(f"  {field + ':':18} {outcome.values[field]}")


async def _extract_specs(slug: str, model: str | None) -> spec_extraction_service.ExtractionOutcome:
    """Async half of `extract-specs`: one session, one service call."""
    async with get_sessionmaker()() as session:
        motorbike = await product_service.get_by_slug(session, slug)
        if motorbike is None:
            _fail(f"No catalogue entry with slug {slug!r}.")
        return await spec_extraction_service.extract_draft_spec(session, motorbike, model=model)


def _fail(message: str) -> NoReturn:
    """Report a typed ingestion failure on stderr and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
