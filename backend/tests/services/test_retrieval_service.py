"""`app/services/retrieval_service.py` — the fusion SQL and its guards.

Hybrid retrieval is one statement whose two legs need a GIN index, an HNSW index
and a `tsvector` column, so the statement itself cannot run without PostgreSQL —
and no test here opens a database connection (see `tests/conftest.py`). What is
therefore tested is everything the service is responsible for *around* the round
trip:

* **the compiled SQL**: both ranked legs, the RRF fusion arithmetic with the
  configured constants, and every filter that must live in the database rather
  than in Python;
* **the mapping**: the ordering and the provenance of what comes back is the
  database's, and the service adds no sorting, filtering or defaulting of its
  own — a `RetrievedChunk` is exactly one returned row;
* **the guards**: a blank query and an empty motorbike list never reach the
  embeddings gateway, and a dimension mismatch names `app embeddings rebuild`.

The fusion *arithmetic* is executed by PostgreSQL, so its numeric behaviour is
proven live (`app retrieval search`) and structurally here.
"""

import asyncio
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import get_settings
from app.db.models.motorbike import MotorbikeStatus
from app.llm import embeddings as llm_embeddings
from app.services import retrieval_service

QUERY = "comfortable touring bike"
BIKE_ID = "01J0BIKE00000000000000000A"
OTHER_BIKE_ID = "01J0BIKE00000000000000000B"

# One fused row, as `result.mappings()` hands it over.
ROW: dict[str, Any] = {
    "chunk_id": "01J0CHUNK0000000000000001",
    "motorbike_id": BIKE_ID,
    "text": "  Wind protection on\nlong trips is excellent.  ",
    "score": 0.032,
    "source_document_id": "01J0DOC000000000000000001",
    "source_url": "https://example.test/review",
    "source_title": "Touring review",
    "heading_path": "Suzuki GSR600 > Comfort",
    "page_number": None,
    "sequence": 4,
}

# `%(name)s` placeholders make an assertion depend on SQLAlchemy's parameter
# numbering; the shape of the statement is what matters here.
_PARAMETER = re.compile(r"%\([a-z_0-9]+\)s")


class StubEmbeddings:
    """Stands in for the OpenRouter embeddings client; records what it saw."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def aembed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return [0.1, 0.2, 0.3]


class _Mappings:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Mappings:
        return _Mappings(self._rows)


class RecordingSession:
    """Stands in for `AsyncSession`: records statements, replays scripted rows.

    The service-level `FakeAsyncSession` interprets the statement shapes the
    other services issue; a CTE-based hybrid query is not one of them, and
    re-implementing RRF in a fake would only test the fake. This stub therefore
    answers with the rows a database would return and keeps the statement for
    inspection.
    """

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows if rows is not None else []
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        return _Result(self.rows)


@pytest.fixture
def embeddings(monkeypatch: pytest.MonkeyPatch) -> StubEmbeddings:
    """Replace the embeddings factory, so no test reaches OpenRouter."""
    stub = StubEmbeddings()
    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: stub)
    return stub


@pytest.fixture
def settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Return a setter for the settings the service reads at call time."""

    def override(**environment: object) -> None:
        for key, value in environment.items():
            monkeypatch.setenv(key, str(value))
        get_settings.cache_clear()

    yield override
    get_settings.cache_clear()


def _search(
    session: RecordingSession,
    query: str = QUERY,
    *,
    motorbike_ids: list[str] | None = None,
    limit: int = retrieval_service.DEFAULT_LIMIT,
) -> list[retrieval_service.RetrievedChunk]:
    """Drive the async service from a synchronous test."""
    return asyncio.run(
        retrieval_service.search(session, query, motorbike_ids=motorbike_ids, limit=limit)
    )


def _compiled(session: RecordingSession) -> Any:
    """Compile the single statement the service issued, for PostgreSQL."""
    assert len(session.statements) == 1, "retrieval must be one round trip"
    return session.statements[0].compile(dialect=postgresql.dialect())


def _sql(session: RecordingSession) -> str:
    """Return the compiled SQL with bound parameters reduced to `?`."""
    return _PARAMETER.sub("?", str(_compiled(session)))


def test_maps_every_provenance_field(embeddings: StubEmbeddings) -> None:
    """A returned row becomes one `RetrievedChunk`, verbatim."""
    session = RecordingSession([dict(ROW)])

    chunks = _search(session)

    assert [chunk.model_dump() for chunk in chunks] == [ROW]
    assert embeddings.queries == [QUERY]


def test_returned_order_is_the_database_ordering(embeddings: StubEmbeddings) -> None:
    """The service never re-sorts: the fused order is the SQL's `ORDER BY`.

    Seeded deliberately with an ascending score, so a Python-side sort by score
    would change the order and fail here.
    """
    rows = [
        {**ROW, "chunk_id": "chunk-a", "score": 0.010},
        {**ROW, "chunk_id": "chunk-b", "score": 0.020},
        {**ROW, "chunk_id": "chunk-c", "score": 0.030},
    ]
    session = RecordingSession([dict(row) for row in rows])

    chunks = _search(session)

    assert [chunk.chunk_id for chunk in chunks] == ["chunk-a", "chunk-b", "chunk-c"]
    assert [chunk.score for chunk in chunks] == [0.010, 0.020, 0.030]


def test_both_legs_are_ranked_and_capped_per_leg(embeddings: StubEmbeddings) -> None:
    """Full-text and vector candidates are ranked, capped and fused in one SQL."""
    session = RecordingSession()

    _search(session)
    sql = _sql(session)

    # The lexical leg: English full-text search over the generated column.
    assert "ts_rank(chunks.text_tsv, plainto_tsquery(?, ?))" in sql
    assert "chunks.text_tsv @@ plainto_tsquery(?, ?)" in sql
    # The semantic leg: pgvector cosine distance, ascending.
    assert "chunks.embedding <=> ?" in sql
    # Each leg ranks its own candidates and is cut to the per-leg budget.
    assert sql.count("row_number() OVER (ORDER BY") == 2
    assert sql.count("LIMIT ?") == 3  # two legs plus the result limit
    assert _compiled(session).params["plainto_tsquery_1"] == "english"


def test_fusion_is_rrf_over_both_ranks_with_configured_constants(
    embeddings: StubEmbeddings, settings_override: Callable[..., None]
) -> None:
    """Each leg contributes `1 / (RRF_K + rank)`; both constants come from config."""
    settings_override(RRF_K=7, RETRIEVAL_CANDIDATES_PER_LEG=3)
    session = RecordingSession()

    _search(session)
    sql = _sql(session)
    params = _compiled(session).params

    assert "FULL OUTER JOIN semantic ON lexical.chunk_id = semantic.chunk_id" in sql
    assert "/ CAST((? + lexical.rank) AS NUMERIC)" in sql
    assert "/ CAST((? + semantic.rank) AS NUMERIC)" in sql
    # A leg that found nothing contributes nothing instead of nulling the sum.
    assert sql.count("coalesce(?") == 2
    assert "ORDER BY fused.score DESC" in sql
    # Not literals: both configured values reach the statement, once per leg.
    assert sorted(value for value in params.values() if value == 7) == [7, 7]
    assert sorted(value for value in params.values() if value == 3) == [3, 3]


def test_every_filter_lives_in_the_sql(embeddings: StubEmbeddings) -> None:
    """Approval, non-null vectors, the embedding model and the id list are SQL."""
    session = RecordingSession()

    _search(session, motorbike_ids=[BIKE_ID, OTHER_BIKE_ID], limit=5)
    sql = _sql(session)
    params = _compiled(session).params

    # Both legs carry the same four filters — a candidate list is never fixed up
    # afterwards in Python.
    assert sql.count("motorbikes.status = ?") == 2
    assert sql.count("chunks.embedding IS NOT NULL") == 2
    assert sql.count("chunks.embedding_model = ?") == 2
    assert sql.count("chunks.motorbike_id IN (__[POSTCOMPILE_motorbike_id_1])") == 2
    assert params["status_1"] is MotorbikeStatus.APPROVED
    assert params["embedding_model_1"] == get_settings().embedding_model
    assert params["motorbike_id_1"] == [BIKE_ID, OTHER_BIKE_ID]
    assert params["param_5"] == 5


def test_unfiltered_search_has_no_motorbike_clause(embeddings: StubEmbeddings) -> None:
    """Without `motorbike_ids` the whole approved catalogue is searched."""
    session = RecordingSession()

    _search(session)

    assert "chunks.motorbike_id IN" not in _sql(session)


@pytest.mark.parametrize(
    ("query", "motorbike_ids"),
    [("   ", None), (QUERY, [])],
    ids=["blank query", "empty motorbike list"],
)
def test_empty_search_space_costs_nothing(
    embeddings: StubEmbeddings, query: str, motorbike_ids: list[str] | None
) -> None:
    """An empty search space is answered without gateway call or query."""
    session = RecordingSession([dict(ROW)])

    assert _search(session, query, motorbike_ids=motorbike_ids) == []
    assert embeddings.queries == []
    assert session.statements == []


def test_dimension_mismatch_names_the_rebuild_command(
    embeddings: StubEmbeddings, settings_override: Callable[..., None]
) -> None:
    """A vector-width mismatch fails before the gateway, naming both fixes."""
    settings_override(EMBEDDING_DIMENSIONS=768)
    session = RecordingSession([dict(ROW)])

    with pytest.raises(retrieval_service.StaleEmbeddingsError) as raised:
        _search(session)

    message = str(raised.value)
    assert "app embeddings rebuild" in message
    assert "EMBEDDING_DIMENSIONS is 768" in message
    assert embeddings.queries == []
    assert session.statements == []
