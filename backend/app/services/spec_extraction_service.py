"""Turn a motorbike's stored source documents into its draft specification.

The service layer half of step 2.17: it decides *what* the model reads (which
documents, in which order, how much of each), runs the extraction chain and
writes the result — as a **draft** specification only. A `verified` row is
never touched here: approval promotes a draft, and nothing else writes verified
specifications (`product_service`).

Two rules live here:

* **The input budget is character-based** (no tokenizer dependency): the
  Wikipedia document comes first, every document is head-truncated to
  `DOCUMENT_MAX_CHARS`, and the total is capped at `EXTRACTION_MAX_INPUT_CHARS`.
  Documents that no longer fit are left out rather than sampled.
* **An extraction failure is never an exception the caller has to handle.** Like
  the ingestion adapters, this service returns a typed failure with a
  warning-ready `detail` (already logged once), so the ingestion job can append
  it to the operation message and still hand the model to review — the admin
  fills the form in by hand, which is the correction mechanism anyway.

Re-running is idempotent by construction: `upsert_draft_spec` is a full-object
replace of the single `draft` row, so a second run replaces the first result
instead of adding anything.

Some extracted fields are not specification columns: the **manufacturer** and
the **identity block** (`buildingline`, `model_name`, `year_from`, `year_to`,
`type_codes`, `variants` — `motorbikes` itself). They are written after, and
only after, the draft specification was written, and never loudly enough to
cost the run its specification.

The identity write additionally follows **D2b**
(`docs/roadmap/stage-01/phase-6/shared-knowledge.md`): `product_service.assign_identity`
is a full-object replace, so this service **merges first** — the row's current
identity wins over the extraction, field by field, and `type_codes` are
unioned. A first ingestion therefore fills everything; a re-ingestion fills
only what is still missing; an admin's correction, once made, is permanent.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.motorbike import Motorbike
from app.db.models.motorbike_spec import MotorbikeSpec
from app.db.models.source_document import SourceDocument, SourceType
from app.llm import extraction
from app.llm.models import MissingApiKeyError
from app.services import (
    document_service,
    identity_validation,
    manufacturer_service,
    product_service,
)

logger = logging.getLogger(__name__)

# Per-document head truncation: specifications live at the top of a page, and a
# long magazine review must not crowd out the manufacturer's data sheet.
DOCUMENT_MAX_CHARS = 12_000

# How the typed failures read in the operation message.
MISSING_DOCUMENTS_DETAIL = "Specification extraction skipped: no source documents to read."
MISSING_KEY_DETAIL = "Specification extraction skipped: OPENROUTER_API_KEY is not configured."
MODEL_ERROR_DETAIL = "Specification extraction failed: {error}"
MAX_ERROR_CHARS = 200


class ExtractionFailureReason(StrEnum):
    """Why one extraction produced no specification."""

    NO_DOCUMENTS = "no_documents"
    MISSING_API_KEY = "missing_api_key"
    MODEL_ERROR = "model_error"


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """A completed extraction and the draft row it wrote."""

    spec: MotorbikeSpec
    extracted: extraction.ExtractedSpec
    values: dict[str, Any]
    documents: int
    # Dropped-entry warnings from `identity_validation.normalize_type_codes` /
    # `normalize_variants`, already logged here. Empty on the manufacturer-only
    # path (`extracted.model_name is None`) and on a failed identity write.
    # Not surfaced to the run's own warnings by this step — 6.17's
    # `_extraction_stage` edit feeds this to `_Run._warn`.
    identity_warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractionFailure:
    """An extraction that produced nothing, with a warning-ready detail."""

    reason: ExtractionFailureReason
    detail: str


ExtractionOutcome = ExtractionResult | ExtractionFailure


def assemble_documents(
    documents: Sequence[SourceDocument], *, max_input_chars: int | None = None
) -> tuple[extraction.ExtractionDocument, ...]:
    """Return the documents to extract from, in order and within the budget.

    Wikipedia first (it is the most reliable single description of a model),
    then the remaining documents in the order they were given. Each is
    head-truncated to `DOCUMENT_MAX_CHARS`, and a document that does not fit
    into what is left of `max_input_chars` is truncated to the remainder; once
    the budget is spent, the rest is dropped.

    `listing` documents never reach the prompt (D12, third carve-out): a used
    ad feeding asking prices into `msrp_eur` — a new-bike field (D9) — is not
    a specification source.
    """
    budget = (
        get_settings().extraction_max_input_chars if max_input_chars is None else max_input_chars
    )
    candidates = [
        document for document in documents if document.source_type is not SourceType.LISTING
    ]
    # Stable: `False` sorts first, so the Wikipedia article keeps its place at
    # the front and everything else keeps the caller's order.
    ordered = sorted(
        candidates, key=lambda document: document.source_type is not SourceType.WIKIPEDIA
    )

    assembled: list[extraction.ExtractionDocument] = []
    remaining = budget
    for document in ordered:
        if remaining <= 0:
            break
        markdown = document.content_markdown.strip()[:DOCUMENT_MAX_CHARS][:remaining]
        if not markdown:
            continue
        remaining -= len(markdown)
        assembled.append(
            extraction.ExtractionDocument(
                title=document.source_title,
                source_type=document.source_type.value,
                markdown=markdown,
                url=document.source_url,
            )
        )
    return tuple(assembled)


async def extract_draft_spec(
    session: AsyncSession,
    motorbike: Motorbike,
    *,
    model: str | None = None,
) -> ExtractionOutcome:
    """Extract `motorbike`'s specification and replace its draft row.

    Args:
        session: Session the write goes through; `upsert_draft_spec` commits.
        motorbike: The catalogue entry whose stored documents are read.
        model: OpenRouter model id; defaults to the configured `CHAT_MODEL`.

    Returns:
        The written draft row, or a typed failure whose `detail` is ready to be
        appended to an operation message. Nothing raised here has to be caught
        by the caller.
    """
    documents = assemble_documents(await document_service.list_for_motorbike(session, motorbike.id))
    if not documents:
        return _failed(ExtractionFailureReason.NO_DOCUMENTS, MISSING_DOCUMENTS_DETAIL, motorbike)

    try:
        extracted = await extraction.extract_spec(motorbike.query_name, documents, model=model)
    except MissingApiKeyError:
        # Deterministic, not transient: retrying cannot configure a key.
        return _failed(ExtractionFailureReason.MISSING_API_KEY, MISSING_KEY_DETAIL, motorbike)
    except Exception as error:
        # A gateway error, a timeout, an unparsable answer: the taxonomy spans
        # the SDK, two HTTP clients and the output parser, and every one of them
        # means the same thing here — no specification, and the run goes on.
        detail = MODEL_ERROR_DETAIL.format(
            error=f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS]
        )
        logger.warning(
            "Specification extraction for motorbike %s failed.", motorbike.id, exc_info=error
        )
        return ExtractionFailure(reason=ExtractionFailureReason.MODEL_ERROR, detail=detail)

    values = extracted.to_spec_values(extracted_at=datetime.now(UTC))
    spec = await product_service.upsert_draft_spec(session, motorbike.id, values)
    identity_warnings = await _assign_identity(session, motorbike, extracted)
    logger.info(
        "Extracted %d specification field(s) for motorbike %s from %d document(s): %s.",
        len(extracted.filled_fields()),
        motorbike.id,
        len(documents),
        ", ".join(extracted.filled_fields()) or "none",
    )
    return ExtractionResult(
        spec=spec,
        extracted=extracted,
        values=values,
        documents=len(documents),
        identity_warnings=identity_warnings,
    )


async def _assign_identity(
    session: AsyncSession, motorbike: Motorbike, extracted: extraction.ExtractedSpec
) -> tuple[str, ...]:
    """Merge the extracted identity into `motorbike` — never at the cost of the run.

    **D2b**: `product_service.assign_identity` is a full-object replace, so
    this caller merges first. Per field, an existing non-NULL value already on
    `motorbike` wins over the extraction (`model_name`, `year_from`,
    `year_to`, `buildingline`, `manufacturer_id`); `type_codes` are the
    **union** of stored and extracted (additive retrieval metadata); `variants`
    is only replaced from an **empty** stored list. So the first ingestion
    fills everything, a re-ingestion fills only what is still missing, and an
    admin's correction is permanent.

    When `extracted.model_name is None`, nothing structured was found: only
    the manufacturer is assigned, exactly as before this step
    (`manufacturer_service.normalize_name` + `get_or_create`, skipped when the
    extraction named none) — `assign_identity` is never called on this path,
    because a full-object replace with every other field `null` would wipe an
    existing identity.

    Any exception — including `DuplicateModelError` on a slug collision — is
    logged once and swallowed: the draft specification always stands and the
    run continues.

    Returns:
        The identity normalisers' dropped-entry warnings (already logged
        here too), empty on the manufacturer-only path or on a failed write.
    """
    if extracted.model_name is None:
        await _assign_manufacturer_only(session, motorbike, extracted.manufacturer)
        return ()

    type_codes, type_code_warnings = identity_validation.normalize_type_codes(extracted.type_codes)
    variants, variant_warnings = identity_validation.normalize_variants(extracted.variants)
    # `assign_identity` re-validates whatever it is handed and only
    # `logger.warning`s a drop, without surfacing it to the caller — so the
    # union below is pre-capped here, through the same normaliser, rather
    # than risking a silent second-stage drop nobody's `identity_warnings`
    # would carry.
    merged_type_codes, cap_warnings = identity_validation.normalize_type_codes(
        sorted(set(motorbike.type_codes or []) | set(type_codes))
    )
    warnings = (*type_code_warnings, *cap_warnings, *variant_warnings)
    for warning in warnings:
        logger.warning("Motorbike %s: %s", motorbike.id, warning)

    try:
        manufacturer_id = await _resolve_manufacturer_id(session, motorbike, extracted.manufacturer)
        await product_service.assign_identity(
            session,
            motorbike,
            manufacturer_id=(
                motorbike.manufacturer_id
                if motorbike.manufacturer_id is not None
                else manufacturer_id
            ),
            buildingline=(
                motorbike.buildingline
                if motorbike.buildingline is not None
                else extracted.buildingline
            ),
            model_name=(
                motorbike.model_name if motorbike.model_name is not None else extracted.model_name
            ),
            year_from=(
                motorbike.year_from if motorbike.year_from is not None else extracted.year_from
            ),
            year_to=motorbike.year_to if motorbike.year_to is not None else extracted.year_to,
            type_codes=merged_type_codes,
            variants=list(motorbike.variants) if motorbike.variants else variants,
        )
    except Exception as error:
        logger.warning(
            "Motorbike %s: extracted identity was not assigned.", motorbike.id, exc_info=error
        )
        return warnings

    logger.info("Motorbike %s: identity merged and assigned from extraction.", motorbike.id)
    return warnings


async def _resolve_manufacturer_id(
    session: AsyncSession, motorbike: Motorbike, name: str | None
) -> str | None:
    """Return the manufacturer id to feed the D2b merge, or `None`.

    Resolves the extracted brand via get-or-create; falls back to the row's
    already-stored `manufacturer_id` when the extraction named none, so the
    merge in `_assign_identity` always has a value to compare against. May
    raise (an unusable name, a write failure) — the caller decides how loud
    that is.
    """
    normalized = manufacturer_service.normalize_name(name)
    if normalized is None:
        return motorbike.manufacturer_id
    manufacturer = await manufacturer_service.get_or_create(session, normalized)
    return manufacturer.id


async def _assign_manufacturer_only(
    session: AsyncSession, motorbike: Motorbike, name: str | None
) -> None:
    """Point `motorbike` at the extracted brand — never at the cost of the run.

    The cheap short-circuit for an extraction with no structured identity
    (`extracted.model_name is None`): the brand is not a specification column,
    it is a `manufacturers` row, so it is written here rather than by
    `upsert_draft_spec`. Nothing about it is worth losing an extraction over —
    an unusable name (`"???"`, which `get_or_create` rejects) or a failing
    write is logged and the draft specification stands. Unlike
    `_assign_identity`'s merge, this is a plain (non-merging) assignment,
    exactly as it was before this step.
    """
    normalized = manufacturer_service.normalize_name(name)
    if normalized is None:
        return

    try:
        manufacturer = await manufacturer_service.get_or_create(session, normalized)
        await product_service.assign_manufacturer(session, motorbike, manufacturer.id)
    except Exception as error:
        logger.warning(
            "Motorbike %s: extracted manufacturer %r was not assigned.",
            motorbike.id,
            normalized,
            exc_info=error,
        )
        return
    logger.info(
        "Motorbike %s assigned to manufacturer %s (%r).",
        motorbike.id,
        manufacturer.id,
        manufacturer.name,
    )


def _failed(
    reason: ExtractionFailureReason, detail: str, motorbike: Motorbike
) -> ExtractionFailure:
    """Log one expected failure once and return it, as the adapters do."""
    logger.warning("Motorbike %s: %s", motorbike.id, detail)
    return ExtractionFailure(reason=reason, detail=detail)
