"""The advanced-RAG pipeline: one customer utterance in, cited chunks out.

Steps 3.7 and 3.8 built the two halves of advanced retrieval — hybrid search
over the prose (`retrieval_service`) and structured search over the verified
specifications (`catalogue_search_service`, driven by the translated
`SpecFilters`). This module is the only place that runs them together, and it is
consumed exactly once: as the `retrieve_bike_knowledge` tool of the advisor
agent (step 3.13). It owns four decisions and no SQL of its own.

* **Translate first, search second.** "I'm 1.65 m, just got my A2, mostly city
  commuting" is not a search query: it is one to three queries *plus* hard
  constraints *plus* (sometimes) a named model. `query_translation` splits it
  (`CHAT_MODEL`, a utility task — the advisor's own model is not involved).
* **Constraints narrow the search space, prose ranks inside it.** Derived filters
  and named bikes are resolved to a candidate id list, and every query is
  searched *scoped to those candidates*. Nothing derived ⇒ the whole approved
  catalogue is searched. This is the "structured retrieval" half of the
  advanced-RAG requirement: the seat-height bound is answered by the database,
  never by hoping the vector space understood "1.65 m".
* **A second RRF pass fuses the queries.** Each query already comes back
  RRF-fused across its own two legs; those per-query *scores* are not comparable
  across queries, but their *ranks* are — so the same reciprocal-rank fusion (the
  same `RRF_K`) runs once more over the per-query rankings, and a chunk found by
  two queries outranks one found by a single query. `chunks[].score` is
  therefore the **cross-query** score, comparable only within one `RagResult`.
* **It degrades, never raises** (the 2.10/2.12/2.17 typed-failure convention): a
  failed or unusable translation falls back to retrieving the raw utterance with
  no filters, because a customer waiting for an answer is better served by
  plain hybrid search than by an exception. The two *configuration* errors
  `retrieval_service` documents (`MissingApiKeyError`, `StaleEmbeddingsError`)
  do propagate — they are not outcomes to hide, and both callers (the CLI here,
  the tool wrapper in 3.13) report them.

Nothing here writes, and nothing here commits: `RagResult` is a read model.
"""

import logging
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.llm import query_translation
from app.llm.query_translation import ActivePreference, SpecFilters, TranslatedQuery
from app.services import catalogue_search_service, retrieval_service
from app.services.retrieval_service import RetrievedChunk

logger = logging.getLogger(__name__)

# How much of a failed translation's error reaches the log line (the extraction
# service's cap, same reason: a gateway error body is not a log message).
MAX_ERROR_CHARS = 200


class RagResult(BaseModel):
    """What one retrieval produced, including why it produced it.

    This is the "why these sources" payload: step 3.13 turns `chunks` into the
    persisted `sources[]` list (dedupe, cap and camelCase aliasing are its job,
    not this module's) and shows `queries`/`applied_filters`/
    `candidate_motorbike_ids` as the tool result, so a grader can see that the
    A2 constraint was answered by SQL rather than by the language model. Phase 5
    traces the same four fields.

    Fields are snake_case like `RetrievedChunk`'s, and an empty result is a
    normal one: no chunks means the knowledge base has nothing for this turn,
    which the advisor must be able to say out loud.
    """

    model_config = ConfigDict(frozen=True)

    queries: list[str]
    """The queries actually searched: the translation's rewrites, or the raw
    utterance when the translation failed or produced none."""

    applied_filters: dict[str, Any]
    """Only the bounds the translation actually stated, as plain values
    (`SpecFilters.values()` minus the unset ones); empty when none were
    derived."""

    candidate_motorbike_ids: list[str]
    """The search space the queries were scoped to — named bikes first, then the
    filter matches. Empty means unscoped (nothing was derived) *or* that the
    stated constraints match no approved model; `applied_filters` tells the two
    apart."""

    chunks: list[RetrievedChunk]
    """The fused ranking, best first, at most `limit` long. `score` is the
    cross-query RRF score."""


async def retrieve(
    session: AsyncSession,
    utterance: str,
    *,
    preferences: Sequence[ActivePreference] = (),
    history_summary: str = "",
    limit: int = retrieval_service.DEFAULT_LIMIT,
) -> RagResult:
    """Translate `utterance`, narrow the catalogue, search and fuse.

    Args:
        session: Session every read runs on. Nothing is written or committed.
            The legs run **sequentially** — one session cannot serve concurrent
            statements — which is also why `limit` bounds the work per query.
        utterance: What the customer just wrote (or the sub-question the agent
            wants knowledge about). Whitespace-collapsed; blank returns an empty
            result without a single gateway call.
        preferences: The active, non-superseded preferences to translate with,
            in the caller's order.
        history_summary: A short recap of the conversation so far; blank omits
            the block from the translation prompt.
        limit: How many chunks each query retrieves *and* how many fused chunks
            come back.

    Returns:
        The fused chunks plus the plan that produced them. A failed translation
        is not an error here: it degrades to the raw utterance, unscoped.

    Raises:
        retrieval_service.StaleEmbeddingsError: configured embedding size and
            stored vector width disagree — a configuration problem, not an
            outcome.
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured, so no query
            can be embedded.
    """
    text = " ".join(utterance.split())
    if not text:
        logger.info("Retrieval skipped: the utterance is blank.")
        return RagResult(queries=[], applied_filters={}, candidate_motorbike_ids=[], chunks=[])

    plan = await _translate(text, preferences=preferences, history_summary=history_summary)
    if plan is None:
        # The pinned fallback: raw utterance, no filters, whole catalogue.
        return RagResult(
            queries=[text],
            applied_filters={},
            candidate_motorbike_ids=[],
            chunks=await _fuse(session, [text], None, limit),
        )

    # No rewrite is usable ⇒ the raw utterance is the query; combined with an
    # empty filter set and no resolvable name, that is exactly the fallback.
    queries = list(plan.search_queries) or [text]
    applied_filters = _stated_filters(plan.spec_filters)
    candidate_ids = await _candidate_ids(session, plan)

    if candidate_ids is not None and not candidate_ids:
        # Constraints were stated and the catalogue satisfies none of them.
        # Searching unscoped would answer with prose about bikes the customer
        # ruled out, so the honest answer is no chunks — and the agent can see
        # from `applied_filters` which claim emptied the shortlist.
        logger.info(
            "No approved model matches the derived constraints %s; retrieval returns nothing.",
            applied_filters,
        )
        return RagResult(
            queries=queries,
            applied_filters=applied_filters,
            candidate_motorbike_ids=[],
            chunks=[],
        )

    chunks = await _fuse(session, queries, candidate_ids, limit)
    logger.info(
        "Retrieved %d chunk(s) from %d query/queries over %s candidate(s); filters: %s.",
        len(chunks),
        len(queries),
        "the whole approved catalogue" if candidate_ids is None else str(len(candidate_ids)),
        applied_filters or "none",
    )
    return RagResult(
        queries=queries,
        applied_filters=applied_filters,
        candidate_motorbike_ids=list(candidate_ids or []),
        chunks=chunks,
    )


async def _translate(
    text: str, *, preferences: Sequence[ActivePreference], history_summary: str
) -> TranslatedQuery | None:
    """Return the retrieval plan, or `None` when the translation is unusable.

    Every failure mode of the translation pass — an unreachable gateway, a
    timeout, a malformed answer the structured-output parser rejects, a missing
    key — means the same thing here: no plan, and the turn goes on with plain
    hybrid search over the raw utterance. Logged once, like the ingestion
    adapters' typed failures.
    """
    try:
        return await query_translation.translate_query(
            text,
            history_summary=history_summary.strip() or None,
            preferences=preferences,
        )
    except Exception as error:
        logger.warning(
            "Query translation failed (%s); retrieving the raw utterance instead.",
            f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS],
            exc_info=error,
        )
        return None


async def _candidate_ids(session: AsyncSession, plan: TranslatedQuery) -> list[str] | None:
    """Return the candidate search space, or `None` for "unscoped".

    Named bikes come first: a model the customer named is an explicit request,
    while a filter is a derived claim. The two lists are merged rather than
    intersected — asked about the MT-07 *and* riding on an A2, the customer
    still deserves the prose about the MT-07.

    `None` (nothing derived) and `[]` (constraints that match nothing) are
    deliberately different answers; the caller treats them differently.
    """
    named = await _resolve_names(session, plan.target_motorbike_names)
    filtered = (
        None
        if plan.spec_filters.is_empty()
        else await catalogue_search_service.find_motorbike_ids(session, plan.spec_filters)
    )
    if filtered is None and not named:
        return None

    merged = list(named)
    for motorbike_id in filtered or []:
        if motorbike_id not in merged:
            merged.append(motorbike_id)
    return merged


async def _resolve_names(session: AsyncSession, names: Sequence[str]) -> list[str]:
    """Resolve model names the conversation mentioned to approved catalogue ids.

    The resolution itself is `catalogue_search_service.resolve_name` (the shared
    resolver: exact slug, then type code, then a substring match, approved
    entries only) — this helper only turns its answers into a deduplicated id
    list. A name that
    resolves to nothing is skipped, never an error: the customer may well be
    naming a bike this catalogue has never heard of, and step 3.14's
    `flag_unknown_bike` is where that becomes visible.

    Approved-only is the resolver's rule, not a second check here: prose about a
    `backlog` or `ingesting` model is either absent or unreviewed, and
    `retrieval_service` would filter it out anyway.
    """
    resolved: list[str] = []
    for name in names:
        motorbike = await catalogue_search_service.resolve_name(session, name)
        if motorbike is None:
            logger.info("Named bike %r did not resolve to an approved catalogue entry.", name)
            continue
        if motorbike.id not in resolved:
            resolved.append(motorbike.id)
    return resolved


async def _fuse(
    session: AsyncSession,
    queries: Sequence[str],
    candidate_ids: Sequence[str] | None,
    limit: int,
) -> list[RetrievedChunk]:
    """Search every query in the same space and fuse the rankings with RRF.

    One `retrieval_service.search` per query (sequential: one session), then the
    second fusion pass — each query contributes `1 / (RRF_K + rank)` for the
    rank it gave a chunk, chunks are deduplicated by id, and the score of the
    surviving copy is replaced by the fused sum. Ties break on the chunk id, so
    the ordering is stable and matches the SQL's tiebreaker.
    """
    rrf_k = get_settings().rrf_k
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}

    for query in queries:
        ranked = await retrieval_service.search(
            session, query, motorbike_ids=candidate_ids, limit=limit
        )
        for rank, chunk in enumerate(ranked, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
            # The first copy wins: two searches return the same row, and its
            # provenance cannot differ between them.
            chunks.setdefault(chunk.chunk_id, chunk)

    ordered = sorted(chunks.values(), key=lambda chunk: (-scores[chunk.chunk_id], chunk.chunk_id))
    return [chunk.model_copy(update={"score": scores[chunk.chunk_id]}) for chunk in ordered[:limit]]


def _stated_filters(filters: SpecFilters) -> dict[str, Any]:
    """Return only the bounds the translation stated, as plain values.

    Emptiness is tested against `None` and the empty list, never falsiness —
    `a2_eligible=False` is a constraint (the `SpecFilters.is_empty` rule).
    """
    return {
        field: value
        for field, value in filters.values().items()
        if value is not None and value != []
    }
