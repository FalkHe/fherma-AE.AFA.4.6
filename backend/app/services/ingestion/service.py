"""Orchestration: everything that turns one catalogue name into review material.

This is the composition layer of the ingestion pipeline. It owns no HTTP, no
extraction and no image handling of its own — it calls the adapters
(`wikipedia`, `search`, `fetch`, `extract`, `storage`, `image_service`,
`embedding_service`) in the pinned order, writes what they produce through the
catalogue services, and reports every step into the operation the admin UI is
watching.

Three rules are implemented here and nowhere else:

* **The milestone sequence is a contract.** 5 % `Looking up Wikipedia`, 15 %
  `Searching the web`, 20–60 % `Fetching sources (n/m)`, 65 % `Processing
  images`, 80 % `Extracting specifications`, 90 % `Generating embeddings`,
  100 % succeeded. The admin UI renders those messages verbatim, so the
  constants below are the wording, not a paraphrase of it.
* **A partial failure is a warning, never a failure.** Every adapter returns a
  typed failure instead of raising, and each one is appended to the operation
  `message` while the run continues. **Zero usable documents** is the one
  deterministic failure: the operation is marked `failed` and the motorbike
  goes back to `backlog` so an admin can retry it. The only exception is a run
  that produced nothing *because the network was in the way* — that raises
  `TransientJobError` and is retried by the broker middleware.
* **A run is a fresh run.** Re-ingestion replaces what an earlier run left:
  previous source documents and images (rows *and* files) are deleted before
  the first new document is written, so a review screen never mixes two runs.

Status changes always go through `product_service.transition` (which announces
`product.updated`), and every stored document announces `document.updated`.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx2
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.base import new_ulid
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import MotorbikeImage
from app.db.models.operation import MAX_PROGRESS, Operation
from app.db.models.source_document import SOURCE_TITLE_LENGTH, SourceDocument, SourceType
from app.jobs import TransientJobError
from app.llm import extraction
from app.services import (
    document_service,
    embedding_service,
    image_service,
    operation_service,
    product_service,
    spec_extraction_service,
)
from app.services.ingestion import extract, fetch, search, storage, wikipedia

logger = logging.getLogger(__name__)

# The pinned milestones: (progress, message). The wording is the contract.
WIKIPEDIA_MILESTONE = (5, "Looking up Wikipedia")
SEARCH_MILESTONE = (15, "Searching the web")
IMAGE_MILESTONE = (65, "Processing images")
EXTRACTION_MILESTONE = (80, "Extracting specifications")
EMBEDDING_MILESTONE = (90, "Generating embeddings")

# The fetch stage spreads its candidates over this band; the message counts
# them as `Fetching sources (n/m)`.
FETCH_PROGRESS_START = 20
FETCH_PROGRESS_END = 60
FETCH_MESSAGE_TEMPLATE = "Fetching sources ({index}/{total})"

# How warnings reach the operation `message`, and how the final message reads
# when a run finished with some sources missing.
WARNING_SEPARATOR = "; "
MESSAGE_WARNING_SEPARATOR = " — "
WARNING_SUMMARY_PREFIX = "Completed with warnings: "

# Error text of the one deterministic failure of a run.
NO_DOCUMENTS_ERROR = "No usable source documents could be ingested."

# Step 6.17 — `motorbikes.suggestion` as research input (D6: an input hint, the
# stored claim is never modified). At most this many claimed links become
# fetch candidates, ahead of the provider's own results; a claimed type code
# adds one extra query template to the provider call.
MAX_SUGGESTED_LINKS = 3
# A claimed reference is technical input, never `WIKIPEDIA` — that source type
# is reserved for the vetted Wikipedia stage (the `_article` pick and the
# extraction trust order both key off it).
SUGGESTED_LINK_SOURCE_TYPE = SourceType.TECHNICAL
MAX_TYPE_CODE_TERMS = 2

# D13 — contradiction between the claim and what the sources actually printed;
# recorded through `_Run._warn`, never a new column or table. Pinned verbatim:
# the review UI (6.27) and QA (6.30) grep for these strings.
CLAIM_YEAR_WARNING = "Suggestion contradicted: claimed years {claimed}, sources say {found}."
CLAIM_CODE_WARNING = (
    "Suggestion contradicted: claimed type codes {claimed}, sources printed {found}."
)

# Failure reasons that mean "the network was in the way", not "there is nothing
# to find". A run that produced no document at all is worth retrying only when
# one of these caused it; anything else (no matching article, an HTTP 404, an
# unextractable page) would fail again identically.
_TRANSIENT_WIKIPEDIA_REASONS = frozenset(
    {
        wikipedia.WikipediaFailureReason.SEARCH_FAILED,
        wikipedia.WikipediaFailureReason.ARTICLE_FETCH_FAILED,
    }
)
_TRANSIENT_FETCH_REASONS = frozenset(
    {
        fetch.FetchFailureReason.TIMEOUT,
        fetch.FetchFailureReason.NETWORK_ERROR,
    }
)


async def ingest(
    session: AsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    *,
    client: httpx2.AsyncClient | None = None,
    gate: fetch.PolitenessGate | None = None,
) -> None:
    """Run one full ingestion for `motorbike`, reporting into `operation`.

    Args:
        session: Session the services write through; they own their commits.
        motorbike: The catalogue entry, expected in `ingesting`.
        operation: Its `queued` operation row, created before the enqueue.
        client: Reuse an existing client (see `fetch.build_client`); when
            omitted, one is created and closed around the whole run, so every
            source of one run shares its connections.
        gate: Politeness gate to honour; defaults to the process-wide one.

    Raises:
        TransientJobError: the run produced nothing because a source could not
            be reached — the broker retries it.
        InvalidTransitionError: the row was not in a state that may finish an
            ingestion (a caller bug, or a concurrent admin write).
    """
    if client is None:
        async with fetch.build_client() as owned_client:
            await ingest(session, motorbike, operation, client=owned_client, gate=gate)
            return

    await operation_service.start(session, operation)
    await _Run(
        session=session, motorbike=motorbike, operation=operation, client=client, gate=gate
    ).execute()


async def abandon(
    session: AsyncSession,
    motorbike: Motorbike,
    operation: Operation,
    error: str,
) -> None:
    """End a failed run: motorbike back to `backlog`, operation `failed`.

    The status moves first, so the admin backlog never shows a failed operation
    next to a row that still claims to be ingesting. A row that is no longer
    `ingesting` (an admin moved it while the job ran) keeps its status: only
    the operation records the failure.
    """
    if motorbike.status is MotorbikeStatus.INGESTING:
        await product_service.transition(session, motorbike, MotorbikeStatus.BACKLOG)
    await operation_service.fail(session, operation, error)
    logger.warning("Ingestion of motorbike %s failed: %s", motorbike.id, error)


@dataclass(slots=True)
class _Run:
    """One ingestion run: the pinned stage sequence plus what it collected."""

    session: AsyncSession
    motorbike: Motorbike
    operation: Operation
    client: httpx2.AsyncClient
    gate: fetch.PolitenessGate | None

    warnings: list[str] = field(default_factory=list)
    """Partial failures, appended to the operation message as they happen."""

    documents: int = 0
    """How many source documents this run stored — zero is the failure case."""

    retryable: bool = False
    """Whether a source failed for a reason that may pass on a retry."""

    async def execute(self) -> None:
        """Walk the pinned stages, then either succeed or end the run."""
        await self._discard_previous_run()

        image = await self._wikipedia_stage()
        candidates = await self._search_stage()
        await self._fetch_stage(candidates)

        if self.documents == 0:
            await self._nothing_ingested()
            return

        await self._image_stage(image)
        await self._extraction_stage()
        await self._embedding_stage()
        await self._complete()

    async def _discard_previous_run(self) -> None:
        """Delete what an earlier run left for this motorbike — rows and files.

        Fresh-run semantics: a retry re-fetches every source, so keeping the
        previous documents would show the admin a mixture of two runs (and
        `motorbike_images` would grow a row per attempt).

        `listing` documents are excluded from both the list and the delete
        (D12, first carve-out): they are researched price provenance, not
        ingestion output, and a re-ingestion must not wipe it or unlink its
        file.
        """
        motorbike_id = self.motorbike.id
        documents = await document_service.list_for_motorbike(
            self.session, motorbike_id, exclude_source_types=(SourceType.LISTING,)
        )
        images = await product_service.list_images(self.session, motorbike_id=motorbike_id)
        if not documents and not images:
            return

        for document in documents:
            _unlink(storage.resolve(document.raw_path))
        for image in images:
            _unlink(image_service.resolve(image.original_path))
            for variant in image_service.VARIANT_WIDTHS:
                _unlink(
                    image_service.resolve(
                        image_service.variant_path(motorbike_id, image.id, variant)
                    )
                )

        await self.session.execute(
            delete(SourceDocument).where(
                SourceDocument.motorbike_id == motorbike_id,
                SourceDocument.source_type != SourceType.LISTING,
            )
        )
        await self.session.execute(
            delete(MotorbikeImage).where(MotorbikeImage.motorbike_id == motorbike_id)
        )
        await self.session.commit()
        logger.info(
            "Discarded %d document(s) and %d image(s) of a previous run of motorbike %s.",
            len(documents),
            len(images),
            motorbike_id,
        )

    async def _wikipedia_stage(self) -> wikipedia.WikipediaImage | None:
        """Store the Wikipedia article and return its lead image, if any."""
        await self._advance(*WIKIPEDIA_MILESTONE)

        outcome = await wikipedia.lookup(
            self.motorbike.query_name, client=self.client, gate=self.gate
        )
        if isinstance(outcome, wikipedia.WikipediaFailure):
            self._warn(outcome.detail)
            self.retryable |= outcome.reason in _TRANSIENT_WIKIPEDIA_REASONS
            return None

        await self._store_document(
            source_type=SourceType.WIKIPEDIA,
            source_title=outcome.page.title,
            source_url=outcome.page.url,
            content=outcome.content,
            markdown=outcome.markdown,
        )
        return outcome.image

    async def _search_stage(self) -> tuple[search.SearchCandidate, ...]:
        """Ask the search provider for the pages to fetch after Wikipedia.

        `motorbikes.suggestion`'s claimed links (D6: an input hint, never
        catalogue data) become fetch candidates *first*, so a provider
        duplicate is the one dropped, not the claim's link. A claimed type
        code adds one extra query template to the provider's own search.
        """
        await self._advance(*SEARCH_MILESTONE)

        suggested = self._suggested_candidates()
        results = await search.get_search_provider().search(
            self.motorbike.query_name,
            client=self.client,
            gate=self.gate,
            templates=self._search_templates(),
        )
        for warning in results.warnings:
            self._warn(warning)
        return _dedupe_by_url((*suggested, *results.candidates))

    def _suggested_candidates(self) -> tuple[search.SearchCandidate, ...]:
        """The first `MAX_SUGGESTED_LINKS` claimed links, as fetch candidates.

        Only the fetch candidate's URL is cleaned of `utm_source` — the stored
        `suggestion` JSON is never modified (D6).
        """
        suggestion = self.motorbike.suggestion
        if not suggestion:
            return ()
        links = suggestion.get("links") or []
        return tuple(
            search.SearchCandidate(
                url=search.strip_utm_source(link),
                title=link,
                source_type=SUGGESTED_LINK_SOURCE_TYPE,
            )
            for link in links[:MAX_SUGGESTED_LINKS]
        )

    def _search_templates(self) -> tuple[search.QueryTemplate, ...]:
        """The pinned templates, plus one extra when the claim names type codes."""
        suggestion = self.motorbike.suggestion
        codes = (suggestion or {}).get("type_codes") or []
        if not codes:
            return search.QUERY_TEMPLATES
        terms = " ".join(codes[:MAX_TYPE_CODE_TERMS])
        extra_template = search.QueryTemplate(
            SourceType.TECHNICAL, f'"{{name}}" {terms} motorcycle specifications'
        )
        return (*search.QUERY_TEMPLATES, extra_template)

    async def _fetch_stage(self, candidates: tuple[search.SearchCandidate, ...]) -> None:
        """Fetch, extract and store every candidate, counting them as it goes."""
        total = len(candidates)
        for index, candidate in enumerate(candidates):
            await self._advance(
                _fetch_progress(index, total),
                FETCH_MESSAGE_TEMPLATE.format(index=index + 1, total=total),
            )
            await self._fetch_candidate(candidate)

    async def _fetch_candidate(self, candidate: search.SearchCandidate) -> None:
        """Store one search candidate, or turn its failure into a warning."""
        outcome = await fetch.fetch_html(candidate.url, client=self.client, gate=self.gate)
        if isinstance(outcome, fetch.FetchFailure):
            self._warn(outcome.detail)
            self.retryable |= outcome.reason in _TRANSIENT_FETCH_REASONS
            return

        extracted = extract.extract_markdown(outcome.text, url=outcome.url)
        if isinstance(extracted, extract.ExtractFailure):
            self._warn(extracted.detail)
            return

        await self._store_document(
            source_type=candidate.source_type,
            source_title=candidate.title,
            # The post-redirect URL: provenance records what actually answered.
            source_url=outcome.url,
            content=outcome.content,
            markdown=extracted.markdown,
        )

    async def _store_document(
        self,
        *,
        source_type: SourceType,
        source_title: str,
        source_url: str,
        content: bytes,
        markdown: str,
    ) -> None:
        """Retain the raw payload, create the row and announce the document.

        The id is generated here because the retained payload is named after
        it (`storage.save_raw_document`), so the file is findable from the row
        and a re-ingestion cannot collide with an older run.
        """
        document_id = new_ulid()
        raw_path = storage.save_raw_document(self.motorbike.id, document_id, content)
        document = await document_service.create_document(
            self.session,
            self.motorbike.id,
            document_id=document_id,
            source_type=source_type,
            source_title=source_title[:SOURCE_TITLE_LENGTH],
            source_url=source_url,
            raw_path=raw_path,
            content_markdown=markdown,
            fetched_at=datetime.now(UTC),
        )
        self.documents += 1

        await operation_service.notify(
            self.session,
            {
                "event": "document.updated",
                "productId": self.motorbike.id,
                "documentId": document.id,
            },
        )
        logger.info(
            "Stored %s document %s (%s) for motorbike %s.",
            source_type.value,
            document.id,
            source_url,
            self.motorbike.id,
        )

    async def _image_stage(self, image: wikipedia.WikipediaImage | None) -> None:
        """Store at most one image per run; a missing one is never a failure."""
        await self._advance(*IMAGE_MILESTONE)

        if image is None:
            logger.info("No image found for motorbike %s.", self.motorbike.id)
            return

        outcome = await image_service.ingest_image(
            self.session,
            self.motorbike.id,
            image.url,
            image.attribution,
            client=self.client,
            gate=self.gate,
        )
        if isinstance(outcome, image_service.ImageFailure):
            self._warn(outcome.detail)

    async def _extraction_stage(self) -> None:
        """Extract the draft specification; a failed extraction is a warning.

        The admin can fill the specification form in by hand — that is the
        correction mechanism for a bad extraction anyway — so nothing here may
        cost the run its documents. A missing `OPENROUTER_API_KEY` is part of
        that: deterministic, reported once, and never a retry.
        """
        await self._advance(*EXTRACTION_MILESTONE)

        outcome = await spec_extraction_service.extract_draft_spec(self.session, self.motorbike)
        if isinstance(outcome, spec_extraction_service.ExtractionFailure):
            self._warn(outcome.detail)
            return

        for warning in outcome.identity_warnings:
            self._warn(warning)
        self._warn_on_suggestion_contradiction(outcome.extracted)

    def _warn_on_suggestion_contradiction(self, extracted: extraction.ExtractedSpec) -> None:
        """D13: record — never resolve — a claim the sources contradict.

        The claim (`motorbike.suggestion`) and the finding (the just-extracted
        values) are compared; neither overwrites the other, the run only
        records both through `_warn` and the reviewer decides.
        """
        suggestion = self.motorbike.suggestion
        if not suggestion:
            return

        claimed_year_from = suggestion.get("year_from")
        if (
            claimed_year_from is not None
            and extracted.year_from is not None
            and (extracted.year_from, extracted.year_to)
            != (claimed_year_from, suggestion.get("year_to"))
        ):
            self._warn(
                CLAIM_YEAR_WARNING.format(
                    claimed=_year_range(claimed_year_from, suggestion.get("year_to")),
                    found=_year_range(extracted.year_from, extracted.year_to),
                )
            )

        claimed_codes = suggestion.get("type_codes") or []
        found_codes = extracted.type_codes
        if claimed_codes and found_codes and not (set(claimed_codes) & set(found_codes)):
            self._warn(
                CLAIM_CODE_WARNING.format(
                    claimed="/".join(claimed_codes), found="/".join(found_codes)
                )
            )

    async def _embedding_stage(self) -> None:
        """Chunk the stored documents and embed them; a failure is a warning.

        Same policy as the extraction stage, and for the same reason: review may
        proceed without a knowledge base, and `app embeddings rebuild` backfills
        what this stage could not produce. Transient gateway failures are
        retried inside `embedding_service` (retrying the *job* would re-fetch
        every source), a missing key is a warning, and only a configured
        dimension that does not match the `chunks.embedding` column escapes as
        an exception — that is a deployment mistake, not a source that was
        unavailable.
        """
        await self._advance(*EMBEDDING_MILESTONE)

        outcome = await embedding_service.rebuild_motorbike(self.session, self.motorbike.id)
        if isinstance(outcome, embedding_service.EmbeddingFailure):
            self._warn(outcome.detail)

    async def _nothing_ingested(self) -> None:
        """End a run that stored no document at all.

        A run blocked by an unreachable source is retried (the same run may
        succeed in five seconds); a run that found nothing to ingest is a
        deterministic failure and goes back to the admin's backlog.
        """
        summary = WARNING_SEPARATOR.join(self.warnings)
        if self.retryable:
            raise TransientJobError(f"{NO_DOCUMENTS_ERROR} {summary}".strip())

        error = f"{NO_DOCUMENTS_ERROR} {summary}".strip()
        await abandon(self.session, self.motorbike, self.operation, error)

    async def _complete(self) -> None:
        """Hand the model to review and close the operation as succeeded.

        The status moves before the operation closes, so the backlog row flips
        to `in_review` in the same moment its progress cell disappears. When
        sources were missing, the final message keeps the warnings: the run
        succeeded, but the admin should know what it did not see.
        """
        if self.warnings:
            await self._advance(
                MAX_PROGRESS,
                WARNING_SUMMARY_PREFIX + WARNING_SEPARATOR.join(self.warnings),
                append_warnings=False,
            )

        await product_service.transition(self.session, self.motorbike, MotorbikeStatus.IN_REVIEW)
        await operation_service.succeed(self.session, self.operation)
        logger.info(
            "Ingestion of motorbike %s stored %d document(s) with %d warning(s).",
            self.motorbike.id,
            self.documents,
            len(self.warnings),
        )

    async def _advance(self, progress: int, message: str, *, append_warnings: bool = True) -> None:
        """Report one milestone, carrying the warnings collected so far."""
        if append_warnings and self.warnings:
            message += MESSAGE_WARNING_SEPARATOR + WARNING_SEPARATOR.join(self.warnings)
        await operation_service.advance(self.session, self.operation, progress, message)

    def _warn(self, detail: str) -> None:
        """Record a partial failure; the adapters already logged it once."""
        self.warnings.append(detail)


def _year_range(year_from: int | None, year_to: int | None) -> str:
    """Render a `(year_from, year_to)` pair for a warning message."""
    if year_from is None:
        return "?"
    return f"{year_from}-{year_to}" if year_to is not None else f"{year_from}-"


def _dedupe_by_url(
    candidates: tuple[search.SearchCandidate, ...],
) -> tuple[search.SearchCandidate, ...]:
    """Drop a later candidate sharing an earlier one's URL, order preserved."""
    seen: set[str] = set()
    deduped: list[search.SearchCandidate] = []
    for candidate in candidates:
        if candidate.url in seen:
            continue
        seen.add(candidate.url)
        deduped.append(candidate)
    return tuple(deduped)


def _fetch_progress(index: int, total: int) -> int:
    """Spread the fetch stage evenly over its pinned progress band."""
    span = FETCH_PROGRESS_END - FETCH_PROGRESS_START
    return FETCH_PROGRESS_START + span * index // total


def _unlink(path: Path) -> None:
    """Delete one retained file, tolerating that it is already gone."""
    try:
        path.unlink(missing_ok=True)
    except OSError as error:  # pragma: no cover - defensive
        # A file we cannot delete is disk clutter, not a reason to fail a run.
        logger.warning("Could not delete %s: %s.", path, type(error).__name__, exc_info=error)
