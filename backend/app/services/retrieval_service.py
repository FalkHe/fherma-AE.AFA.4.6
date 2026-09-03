"""Hybrid retrieval over the chunked knowledge base.

The advisor never answers from the model's memory: every claim about a bike has
to come back from a stored chunk that can be shown to the user. This module is
where that lookup happens — one search over both halves of the knowledge base:

* the **lexical** half, PostgreSQL full-text search over the generated
  `chunks.text_tsv` column (GIN index), which finds the exact words a rider
  typed — model names, "A2", "chain adjuster";
* the **semantic** half, pgvector cosine distance over `chunks.embedding` (HNSW
  index), which finds the paraphrase — "comfortable for long trips" matching
  prose about wind protection.

Three rules live here:

* **One SQL statement.** Both legs, the fusion and every filter are a single
  round trip: the two legs must see the same snapshot, and fusing in Python
  would mean shipping candidate rows only to throw most of them away.
* **Filtering is the database's job.** `motorbikes.status = 'approved'`, the
  non-null embedding, the embedding model and the optional motorbike list are
  `WHERE` clauses inside both legs — never a post-filter over the result, which
  would silently shrink a page of results below its limit and leak unapproved
  prose into the ranking.
* **Fusion is Reciprocal Rank Fusion**, not a weighted sum of raw scores: a
  `ts_rank` and a cosine distance are not comparable quantities, but their
  *ranks* are. Each leg contributes `1 / (RRF_K + rank)`; a chunk found by both
  legs therefore outranks one found by a single leg, without either leg's score
  scale mattering.

"Chunked but unembedded" is a normal state (a rebuild always finishes chunking,
even when the embeddings gateway is unusable), so the non-null-embedding filter
is load-bearing and must stay.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Float, Select, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.chunk import TEXT_SEARCH_CONFIGURATION, Chunk
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.source_document import SourceDocument
from app.llm import embeddings as llm_embeddings
from app.services import embedding_service

# How many results one search returns by default. A function parameter on
# purpose, not configuration: every caller knows how many chunks its prompt
# budget affords.
DEFAULT_LIMIT = 10


class StaleEmbeddingsError(RuntimeError):
    """Stored vectors cannot be searched with the configured embedding size.

    Raised instead of running a query that would compare vectors of different
    widths (PostgreSQL would reject it) or silently return nothing. The message
    keeps the migration instructions of the underlying guard and adds the
    command that refills the vectors afterwards.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            f"{detail} Once configuration and column width agree, refill the "
            f"vectors with `app embeddings rebuild` — retrieval only reads "
            f"chunks embedded with the configured EMBEDDING_MODEL."
        )
        self.detail = detail


class RetrievedChunk(BaseModel):
    """One chunk the search returned, with everything needed to cite it.

    The provenance set is fixed: the UI shows a source list, so a retrieved
    chunk that cannot say where it came from is useless. `score` is the fused
    RRF score — comparable within one result list, meaningless across two.
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    motorbike_id: str
    text: str
    score: float
    source_document_id: str
    source_url: str | None
    source_title: str
    heading_path: str | None
    page_number: int | None
    sequence: int


async def search(
    session: AsyncSession,
    query_text: str,
    *,
    motorbike_ids: Sequence[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[RetrievedChunk]:
    """Return the best chunks for `query_text`, best first.

    Args:
        session: Session the single statement is executed on; nothing is
            written, so no transaction is committed here.
        query_text: What the rider (or a translated sub-question) asked. Both
            legs read it: verbatim for full-text search, embedded for the
            vector leg. Blank input returns no results without calling the
            embeddings gateway.
        motorbike_ids: Restrict the search to these catalogue entries; `None`
            searches the whole approved catalogue. An empty sequence is an
            empty search space and returns nothing.
        limit: How many fused results to return.

    Returns:
        Up to `limit` chunks ordered by fused score, descending.

    Raises:
        StaleEmbeddingsError: the configured embedding size and the
            `chunks.embedding` column width disagree.
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured, so the
            query cannot be embedded.
    """
    try:
        embedding_service.require_matching_dimensions()
    except embedding_service.DimensionMismatchError as error:
        raise StaleEmbeddingsError(str(error)) from error

    text = query_text.strip()
    if not text or (motorbike_ids is not None and not motorbike_ids):
        return []

    query_vector = await llm_embeddings.get_embeddings().aembed_query(text)
    statement = _build_statement(text, query_vector, motorbike_ids=motorbike_ids, limit=limit)
    result = await session.execute(statement)
    # The database ordered and cut the list; Python only maps it.
    return [RetrievedChunk(**row) for row in result.mappings().all()]


def _build_statement(
    query_text: str,
    query_vector: Sequence[float],
    *,
    motorbike_ids: Sequence[str] | None,
    limit: int,
) -> Select[tuple[str, str, str, float, str, str | None, str, str | None, int | None, int]]:
    """Compose the one hybrid-retrieval statement.

    Split out from `search` so the SQL can be read (and compiled in a test) on
    its own: two ranked candidate CTEs, a full outer join that keeps chunks
    found by either leg, and the RRF sum as the ordering key.
    """
    settings = get_settings()
    candidates = settings.retrieval_candidates_per_leg
    rrf_k = settings.rrf_k

    # Both legs share these; every one of them belongs in the database.
    filters = [
        Motorbike.status == MotorbikeStatus.APPROVED,
        # A rebuild writes chunks before vectors, so unembedded rows are normal.
        Chunk.embedding.is_not(None),
        # Vectors from a different model are not comparable with this query's.
        Chunk.embedding_model == settings.embedding_model,
    ]
    if motorbike_ids is not None:
        filters.append(Chunk.motorbike_id.in_(list(motorbike_ids)))

    # English on purpose: the corpus is English prose and the generated column
    # was built with the same configuration. No language detection.
    tsquery = func.plainto_tsquery(TEXT_SEARCH_CONFIGURATION, query_text)
    lexical_rank = func.ts_rank(Chunk.text_tsv, tsquery)
    lexical = (
        select(
            Chunk.id.label("chunk_id"),
            # Ranked by the same expression the rows are cut by, so the rank of
            # a returned row never depends on how many rows were considered.
            func.row_number().over(order_by=(lexical_rank.desc(), Chunk.id)).label("rank"),
        )
        .join(Motorbike, Motorbike.id == Chunk.motorbike_id)
        .where(*filters, Chunk.text_tsv.bool_op("@@")(tsquery))
        .order_by(lexical_rank.desc(), Chunk.id)
        .limit(candidates)
        .cte("lexical")
    )

    distance = Chunk.embedding.cosine_distance(query_vector)
    semantic = (
        select(
            Chunk.id.label("chunk_id"),
            func.row_number().over(order_by=(distance, Chunk.id)).label("rank"),
        )
        .join(Motorbike, Motorbike.id == Chunk.motorbike_id)
        .where(*filters)
        .order_by(distance, Chunk.id)
        .limit(candidates)
        .cte("semantic")
    )

    # Full outer join: a chunk that only one leg found still competes, with the
    # missing leg contributing nothing.
    fused = (
        select(
            func.coalesce(lexical.c.chunk_id, semantic.c.chunk_id).label("chunk_id"),
            # Cast to double precision: the division is numeric otherwise, and
            # a score is a float everywhere above this line.
            cast(
                func.coalesce(1.0 / (rrf_k + lexical.c.rank), 0.0)
                + func.coalesce(1.0 / (rrf_k + semantic.c.rank), 0.0),
                Float,
            ).label("score"),
        )
        .select_from(
            lexical.join(
                semantic,
                lexical.c.chunk_id == semantic.c.chunk_id,
                isouter=True,
                full=True,
            )
        )
        .cte("fused")
    )

    return (
        select(
            Chunk.id.label("chunk_id"),
            Chunk.motorbike_id.label("motorbike_id"),
            Chunk.text.label("text"),
            fused.c.score.label("score"),
            Chunk.source_document_id.label("source_document_id"),
            SourceDocument.source_url.label("source_url"),
            SourceDocument.source_title.label("source_title"),
            Chunk.heading_path.label("heading_path"),
            Chunk.page_number.label("page_number"),
            Chunk.sequence.label("sequence"),
        )
        .select_from(fused)
        .join(Chunk, Chunk.id == fused.c.chunk_id)
        .join(SourceDocument, SourceDocument.id == Chunk.source_document_id)
        # The id tiebreaker keeps two equally scored chunks in a stable order.
        .order_by(fused.c.score.desc(), Chunk.id)
        .limit(limit)
    )
