"""QA coverage for `app.services.retrieval_service`, extending the dev agent's
own `test_retrieval_service.py` rather than duplicating its assertions.

The dev file already proves: both legs' shape, the RRF formula with the
configured constants, ordering, the empty-input short circuits, and the
dimension-mismatch guard message. Its filter test counts occurrences of each
filter across the *whole* compiled statement (`sql.count(...) == 2`) — true
today, but that only proves a filter appears twice somewhere, not that each
occurrence sits inside a *different* CTE's `WHERE` (a bug could duplicate a
filter into one leg and never write it into the other, and a whole-string
count would not catch it). This file targets exactly the gaps that leaves
open:

* per-leg isolation of all four filters, by literally splitting the compiled
  SQL at each CTE's boundary and inspecting each half independently;
* the ORDER BY tiebreaker (`chunks.id`) inside *each* leg's own ranking, not
  only in the outer fused ORDER BY;
* the per-leg candidate cap and the final result limit are independently
  controllable — proven with two settings that disagree, reading LIMIT
  values off the statement by their position in the SQL text rather than by
  a specific bind-parameter name (robust to SQLAlchemy's internal naming);
* `RetrievedChunk`'s field set matches the pinned provenance list exactly,
  asserted against the model schema itself rather than inferred from one
  seeded row round-tripping successfully;
* `DEFAULT_LIMIT` is really 10, and the service is really the only round
  trip issued (one `execute` call).

Reuses the dev's `RecordingSession`/`StubEmbeddings`/fixtures rather than
re-implementing them, per the Landed-decisions note in
`docs/roadmap/phase-3/shared-knowledge.md` (Step 3.7): the point of that stub
is exactly to avoid re-deriving RRF arithmetic in a fake session.
"""

import re
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.services import retrieval_service
from tests.services.test_retrieval_service import (
    BIKE_ID,
    QUERY,
    RecordingSession,
    StubEmbeddings,
    _compiled,
    _search,
    _sql,
)
from tests.services.test_retrieval_service import (
    embeddings as embeddings,  # re-exported fixture
)
from tests.services.test_retrieval_service import (
    settings_override as settings_override,  # re-exported fixture
)

PINNED_PROVENANCE_FIELDS = {
    "chunk_id",
    "motorbike_id",
    "text",
    "score",
    "source_document_id",
    "source_url",
    "source_title",
    "heading_path",
    "page_number",
    "sequence",
}


def _cte_blocks(sql: str) -> dict[str, str]:
    """Split the compiled SQL into its three CTE bodies, by literal boundary.

    `_build_statement` always emits `WITH lexical AS (... ), semantic AS
    (... ), fused AS (...) SELECT ...` in that order (verified against the
    actual compiled output before writing this), so slicing on the CTE
    keywords isolates each leg without needing a SQL parser.
    """
    lexical_start = sql.index("lexical AS")
    semantic_start = sql.index("semantic AS")
    fused_start = sql.index("fused AS")
    assert lexical_start < semantic_start < fused_start, "unexpected CTE order"
    return {
        "lexical": sql[lexical_start:semantic_start],
        "semantic": sql[semantic_start:fused_start],
    }


_LIMIT_PARAM = re.compile(r"LIMIT %\((\w+)\)s")


def _limit_values_in_order(session: RecordingSession) -> list[Any]:
    """Read every `LIMIT` clause's bound value, left to right in the SQL text.

    Positional rather than name-based: SQLAlchemy's compiled parameter names
    (`param_3`, `param_4`, ...) are an implementation detail of how many other
    literals were bound before them, and would silently renumber if an
    unrelated part of the statement changed.
    """
    compiled = _compiled(session)
    sql = str(compiled)
    names = [match.group(1) for match in _LIMIT_PARAM.finditer(sql)]
    return [compiled.params[name] for name in names]


# --- per-leg filter isolation ---------------------------------------------


def test_all_four_filters_are_present_in_the_lexical_legs_where_clause(
    embeddings: StubEmbeddings,
) -> None:
    session = RecordingSession()

    _search(session, motorbike_ids=[BIKE_ID], limit=5)
    lexical = _cte_blocks(_sql(session))["lexical"]

    assert "motorbikes.status = ?" in lexical
    assert "chunks.embedding IS NOT NULL" in lexical
    assert "chunks.embedding_model = ?" in lexical
    assert "chunks.motorbike_id IN (__[POSTCOMPILE_motorbike_id_1])" in lexical
    # And the leg's own reason for existing: the full-text predicate.
    assert "chunks.text_tsv @@ plainto_tsquery(?, ?)" in lexical


def test_all_four_filters_are_present_in_the_semantic_legs_where_clause(
    embeddings: StubEmbeddings,
) -> None:
    session = RecordingSession()

    _search(session, motorbike_ids=[BIKE_ID], limit=5)
    semantic = _cte_blocks(_sql(session))["semantic"]

    assert "motorbikes.status = ?" in semantic
    assert "chunks.embedding IS NOT NULL" in semantic
    assert "chunks.embedding_model = ?" in semantic
    assert "chunks.motorbike_id IN (__[POSTCOMPILE_motorbike_id_1])" in semantic
    # The semantic leg must NOT carry the lexical predicate — proves the two
    # legs are genuinely different queries, not the same WHERE list applied
    # to one CTE and copy-pasted with a stray FTS clause into the other.
    assert "text_tsv" not in semantic


def test_filters_do_not_leak_into_the_outer_fused_select(embeddings: StubEmbeddings) -> None:
    """Filtering is the legs' job; the outer select only fuses and joins."""
    session = RecordingSession()

    _search(session, motorbike_ids=[BIKE_ID])
    sql = _sql(session)
    outer = sql[sql.index("fused AS") :]
    # After the fused CTE closes, only the final SELECT/JOIN/ORDER/LIMIT
    # remains; none of the four filters should reappear there.
    after_fused_cte = outer[outer.index(")") + 1 :]

    assert "motorbikes.status" not in after_fused_cte
    assert "embedding_model" not in after_fused_cte
    assert "IS NOT NULL" not in after_fused_cte


# --- deterministic tiebreaker, inside each leg's own ranking --------------


def test_each_legs_row_number_breaks_ties_on_chunk_id(embeddings: StubEmbeddings) -> None:
    """A tie in `ts_rank`/cosine distance must not make a leg's rank flap."""
    session = RecordingSession()

    _search(session)
    blocks = _cte_blocks(_sql(session))

    assert "DESC, chunks.id) AS rank" in blocks["lexical"]
    assert "?, chunks.id) AS rank" in blocks["semantic"]


def test_final_ordering_breaks_ties_on_chunk_id(embeddings: StubEmbeddings) -> None:
    session = RecordingSession()

    _search(session)

    assert "ORDER BY fused.score DESC, chunks.id" in _sql(session)


# --- caps are independently controllable, not the same number twice ------


def test_per_leg_cap_and_final_limit_are_independently_honoured(
    embeddings: StubEmbeddings, settings_override: Any
) -> None:
    """`RETRIEVAL_CANDIDATES_PER_LEG` and `limit` are different knobs."""
    settings_override(RETRIEVAL_CANDIDATES_PER_LEG=17)
    session = RecordingSession()

    _search(session, limit=5)

    lexical_cap, semantic_cap, final_limit = _limit_values_in_order(session)
    assert lexical_cap == 17
    assert semantic_cap == 17
    assert final_limit == 5
    assert final_limit != lexical_cap


def test_default_limit_and_default_candidates_per_leg_reach_the_statement(
    embeddings: StubEmbeddings,
) -> None:
    session = RecordingSession()

    _search(session)

    lexical_cap, semantic_cap, final_limit = _limit_values_in_order(session)
    settings = get_settings()
    assert (lexical_cap, semantic_cap) == (
        settings.retrieval_candidates_per_leg,
        settings.retrieval_candidates_per_leg,
    )
    assert final_limit == retrieval_service.DEFAULT_LIMIT == 10


# --- RetrievedChunk's field set is exactly the pinned provenance set ------


def test_retrieved_chunk_field_set_matches_the_pinned_provenance_list() -> None:
    assert set(retrieval_service.RetrievedChunk.model_fields) == PINNED_PROVENANCE_FIELDS


def test_retrieved_chunk_is_frozen() -> None:
    chunk = retrieval_service.RetrievedChunk(
        chunk_id="c",
        motorbike_id="m",
        text="t",
        score=0.1,
        source_document_id="d",
        source_url=None,
        source_title="s",
        heading_path=None,
        page_number=None,
        sequence=0,
    )
    with pytest.raises(ValidationError):
        chunk.score = 0.9  # type: ignore[misc]


# --- one round trip, no matter the inputs ---------------------------------


def test_search_issues_exactly_one_statement(embeddings: StubEmbeddings) -> None:
    session = RecordingSession()

    _search(session, motorbike_ids=[BIKE_ID], limit=3)

    assert len(session.statements) == 1


def test_search_embeds_the_stripped_query_text_only_once(embeddings: StubEmbeddings) -> None:
    session = RecordingSession()

    _search(session, f"  {QUERY}  ")

    assert embeddings.queries == [QUERY]
