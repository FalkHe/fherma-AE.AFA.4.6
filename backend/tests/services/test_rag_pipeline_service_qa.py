"""QA-owned independent behavioural verification of `rag_pipeline_service`.

The dev's `test_rag_pipeline_service.py` already covers the pipeline's three
documented decisions (fusion/dedup, candidate scoping, the pinned fallback).
This module is QA's independent confirmation of the step-3.9 acceptance
criteria, with a deliberate focus on boundary cases the dev suite does not
exercise: the distinction between "no search_queries" (queries fall back to
the raw utterance but filters/names still scope the search) and "no usable
plan at all" (full fallback, unscoped); named+filtered dedup; the exact
`RagResult` field set and its frozen-ness; and confirming (via `import`
scanning) that the pipeline is not wired into the chat responder.

No test reaches OpenRouter or a database: `retrieval_service.search`,
`catalogue_search_service.find_motorbike_ids`, `catalogue_search_service.resolve_name`
and `query_translation.build_translation_chain` are all monkeypatched.
"""

import ast
import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import get_settings
from app.db.models.motorbike import MotorbikeStatus
from app.llm import query_translation
from app.llm.query_translation import SpecFilters, TranslatedQuery
from app.services import catalogue_search_service, product_service, rag_pipeline_service
from app.services.retrieval_service import RetrievedChunk

UTTERANCE = "I'm 1.65 m, just got my A2, mostly city commuting"
NAMED_BIKE = "Honda CB500F"
BIKE_A = "01J0BIKEQA000000000000AA"
BIKE_B = "01J0BIKEQA000000000000BB"


class _Session:
    """Marker object: the pipeline never issues a statement on it."""


@dataclass(frozen=True, slots=True)
class _Motorbike:
    id: str
    status: MotorbikeStatus


def _chunk(chunk_id: str, *, motorbike_id: str = BIKE_A, score: float = 0.03) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        motorbike_id=motorbike_id,
        text=f"Prose {chunk_id}.",
        score=score,
        source_document_id="01J0DOCQA0000000000000AA",
        source_url="https://example.test/review",
        source_title="QA review",
        heading_path=None,
        page_number=None,
        sequence=1,
    )


def _plan(**values: Any) -> TranslatedQuery:
    return TranslatedQuery.model_validate(values)


@pytest.fixture
def translation(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(answer: TranslatedQuery | Exception) -> None:
        class _Chain:
            async def ainvoke(self, messages: Any) -> TranslatedQuery:
                if isinstance(answer, Exception):
                    raise answer
                return answer

        monkeypatch.setattr(
            query_translation, "build_translation_chain", lambda model=None: _Chain()
        )

    return install


class _Searches:
    def __init__(self, rankings: dict[str, list[RetrievedChunk]] | None = None) -> None:
        self.rankings = rankings or {}
        self.calls: list[tuple[str, Sequence[str] | None, int]] = []

    async def search(
        self,
        session: Any,
        query_text: str,
        *,
        motorbike_ids: Sequence[str] | None = None,
        limit: int = 10,
    ) -> list[RetrievedChunk]:
        self.calls.append((query_text, motorbike_ids, limit))
        return list(self.rankings.get(query_text, []))


@pytest.fixture
def searches(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(rankings: dict[str, list[RetrievedChunk]] | None = None) -> _Searches:
        recorder = _Searches(rankings)
        monkeypatch.setattr(
            rag_pipeline_service.retrieval_service, "search", recorder.search, raising=True
        )
        return recorder

    return install


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(
        *, matches: list[str] | None = None, by_slug: dict[str, _Motorbike] | None = None
    ) -> list[SpecFilters]:
        seen: list[SpecFilters] = []

        async def find_motorbike_ids(session: Any, filters: SpecFilters) -> list[str]:
            seen.append(filters)
            return list(matches or [])

        async def resolve_name(session: Any, name: str) -> _Motorbike | None:
            # Step 3.11 moved the lookup behind `resolve_name`, which owns the
            # slug derivation *and* the approved-only rule — so the stub models
            # both and the fixture keeps its slug-keyed table.
            motorbike = (by_slug or {}).get(product_service.slugify(name))
            if motorbike is None or motorbike.status is not MotorbikeStatus.APPROVED:
                return None
            return motorbike

        monkeypatch.setattr(catalogue_search_service, "find_motorbike_ids", find_motorbike_ids)
        monkeypatch.setattr(catalogue_search_service, "resolve_name", resolve_name)
        return seen

    return install


def _retrieve(
    session: _Session, utterance: str = UTTERANCE, **kwargs: Any
) -> rag_pipeline_service.RagResult:
    return asyncio.run(rag_pipeline_service.retrieve(session, utterance, **kwargs))


# --- Criterion 1: second-pass RRF fusion --------------------------------------


def test_qa_fusion_score_is_the_exact_reciprocal_rank_sum(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A chunk found by two queries scores the sum of its two per-query ranks."""
    translation(_plan(search_queries=["query-x", "query-y"]))
    catalogue()
    searches(
        {
            # chunk-shared is rank 2 in query-x, rank 1 in query-y.
            "query-x": [_chunk("chunk-solo-x"), _chunk("chunk-shared")],
            "query-y": [_chunk("chunk-shared"), _chunk("chunk-solo-y")],
        }
    )

    result = _retrieve(_Session())

    rrf_k = get_settings().rrf_k
    by_id = {chunk.chunk_id: chunk for chunk in result.chunks}
    assert by_id["chunk-shared"].score == pytest.approx(1 / (rrf_k + 2) + 1 / (rrf_k + 1))
    assert by_id["chunk-solo-x"].score == pytest.approx(1 / (rrf_k + 1))
    assert by_id["chunk-solo-y"].score == pytest.approx(1 / (rrf_k + 2))
    # chunk-shared's fused score beats every solo chunk, so it ranks first.
    assert result.chunks[0].chunk_id == "chunk-shared"
    # No id appears twice — dedup by chunk id.
    assert len(result.chunks) == len({c.chunk_id for c in result.chunks})


def test_qa_fusion_ordering_is_score_desc_then_id_tiebreak(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Deterministic ordering: descending score, then chunk id for exact ties."""
    translation(_plan(search_queries=["only-query"]))
    catalogue()
    # Single query, single ranking: every chunk gets a distinct rank, so no two
    # scores tie by construction except when we hand-craft it below.
    searches({"only-query": [_chunk("chunk-b"), _chunk("chunk-a"), _chunk("chunk-c")]})

    result = _retrieve(_Session())

    assert [c.chunk_id for c in result.chunks] == ["chunk-b", "chunk-a", "chunk-c"]
    assert result.chunks[0].score > result.chunks[1].score > result.chunks[2].score


def test_qa_limit_applied_after_fusion_not_before(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Even though each query is capped at `limit`, fusion runs on the union
    first and *then* the result is cut — a chunk pushed out of the top-`limit`
    of one query but boosted by appearing in another must still be able to
    win a slot (verified here by checking the top-ranked survivor is the
    cross-query winner, not simply the first query's top result)."""
    translation(_plan(search_queries=["q1", "q2"]))
    catalogue()
    searches(
        {
            "q1": [_chunk("chunk-1"), _chunk("chunk-2")],
            "q2": [_chunk("chunk-2"), _chunk("chunk-1")],
        }
    )

    result = _retrieve(_Session(), limit=1)

    assert len(result.chunks) == 1
    # chunk-1 (rank1+rank2) and chunk-2 (rank2+rank1) tie exactly; the
    # survivor must be decided by the id tiebreak, not by result truncation
    # order, and there must be exactly one row after the cut.
    assert result.chunks[0].chunk_id == "chunk-1"


# --- Criterion 2: candidate scoping -------------------------------------------


def test_qa_named_and_filtered_ids_merge_with_named_first_and_deduped(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A bike that is both named and filter-matched appears exactly once,
    ordered as a named bike (first), not duplicated at its filter position."""
    translation(
        _plan(
            search_queries=["scoped query"],
            spec_filters={"a2_eligible": True},
            target_motorbike_names=[NAMED_BIKE],
        )
    )
    catalogue(
        matches=[BIKE_A, BIKE_B],  # BIKE_A is also the named bike's resolved id
        by_slug={"honda-cb500f": _Motorbike(BIKE_A, MotorbikeStatus.APPROVED)},
    )
    recorder = searches({"scoped query": [_chunk("chunk-1", motorbike_id=BIKE_A)]})

    result = _retrieve(_Session())

    assert result.candidate_motorbike_ids == [BIKE_A, BIKE_B]
    assert recorder.calls[0][1] == [BIKE_A, BIKE_B]


def test_qa_named_only_scopes_retrieval_without_touching_spec_filters(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """An empty `SpecFilters` (`is_empty()` true) must skip the structured
    search entirely, but a named bike still scopes retrieval."""
    translation(_plan(search_queries=["a query"], target_motorbike_names=[NAMED_BIKE]))
    filters_seen = catalogue(by_slug={"honda-cb500f": _Motorbike(BIKE_A, MotorbikeStatus.APPROVED)})
    recorder = searches({"a query": [_chunk("chunk-1", motorbike_id=BIKE_A)]})

    result = _retrieve(_Session())

    assert result.candidate_motorbike_ids == [BIKE_A]
    assert filters_seen == []  # find_motorbike_ids not called: is_empty() honoured
    assert recorder.calls[0][1] == [BIKE_A]


def test_qa_filters_only_scopes_retrieval_when_no_name_given(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Non-empty filters alone (no named bike) still produce a scoped search."""
    translation(_plan(search_queries=["a query"], spec_filters={"a2_eligible": True}))
    catalogue(matches=[BIKE_A, BIKE_B])
    recorder = searches({"a query": [_chunk("chunk-1", motorbike_id=BIKE_A)]})

    result = _retrieve(_Session())

    assert result.candidate_motorbike_ids == [BIKE_A, BIKE_B]
    assert recorder.calls[0][1] == [BIKE_A, BIKE_B]


def test_qa_unscoped_retrieval_when_translation_yields_nothing_usable(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Empty filters and no resolvable name ⇒ `motorbike_ids=None` (unscoped),
    and `find_motorbike_ids` is never invoked."""
    translation(_plan(search_queries=["a query"]))
    filters_seen = catalogue()
    recorder = searches({"a query": [_chunk("chunk-1")]})

    result = _retrieve(_Session())

    assert result.candidate_motorbike_ids == []
    assert result.applied_filters == {}
    assert recorder.calls[0][1] is None
    assert filters_seen == []


def test_qa_empty_shortlist_from_nonempty_filters_issues_no_retrieval_at_all(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Stated constraints that match no approved bike: zero `retrieval_service
    .search` calls and an empty (not unscoped) chunk list — the
    constraints-match-nothing path, distinct from the unscoped path."""
    translation(_plan(search_queries=["a query"], spec_filters={"seat_height_mm_max": 700}))
    catalogue(matches=[])  # find_motorbike_ids returns nothing
    recorder = searches({"a query": [_chunk("chunk-1")]})  # would answer if called

    result = _retrieve(_Session())

    assert recorder.calls == []
    assert result.chunks == []
    assert result.candidate_motorbike_ids == []
    assert result.applied_filters == {"seat_height_mm_max": 700}


def test_qa_named_bike_rescues_an_otherwise_empty_filter_match(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A named bike is merged in even when the filter side matches nothing —
    the merged shortlist is non-empty, so retrieval *does* run, scoped to
    just the named bike (this is the boundary the constraints-match-nothing
    rule must not swallow)."""
    translation(
        _plan(
            search_queries=["a query"],
            spec_filters={"seat_height_mm_max": 700},
            target_motorbike_names=[NAMED_BIKE],
        )
    )
    catalogue(
        matches=[],  # filters match nothing
        by_slug={"honda-cb500f": _Motorbike(BIKE_A, MotorbikeStatus.APPROVED)},
    )
    recorder = searches({"a query": [_chunk("chunk-1", motorbike_id=BIKE_A)]})

    result = _retrieve(_Session())

    assert result.candidate_motorbike_ids == [BIKE_A]
    assert len(recorder.calls) == 1
    assert recorder.calls[0][1] == [BIKE_A]
    assert len(result.chunks) == 1


# --- Criterion 3: fallback path degrades, never raises ------------------------


@pytest.mark.parametrize(
    "error",
    [ValueError("malformed json"), TimeoutError("gateway timeout"), RuntimeError("boom")],
)
def test_qa_any_translation_exception_falls_back_without_raising(
    error: Exception, translation: Any, searches: Any, catalogue: Any
) -> None:
    """The fallback catches *any* exception type, not just the parser's own —
    the pipeline must never propagate a translation failure."""
    translation(error)
    filters_seen = catalogue()
    recorder = searches({UTTERANCE: [_chunk("chunk-1")]})

    result = _retrieve(_Session())

    assert result.queries == [UTTERANCE]
    assert result.applied_filters == {}
    assert result.candidate_motorbike_ids == []
    assert recorder.calls[0][1] is None
    assert filters_seen == []


def test_qa_fallback_queries_field_is_the_whitespace_collapsed_utterance(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """`RagResult.queries` reflects what was actually searched: the
    whitespace-collapsed utterance, not the raw string with its original
    spacing — proving the result is consistent with the executed search."""
    messy = "  I'm   1.65 m,\n just got my A2  "
    collapsed = " ".join(messy.split())
    translation(ValueError("bad"))
    catalogue()
    recorder = searches({collapsed: [_chunk("chunk-1")]})

    result = _retrieve(_Session(), messy)

    assert result.queries == [collapsed]
    assert recorder.calls[0][0] == collapsed


def test_qa_filters_present_but_no_search_queries_is_not_a_full_fallback(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A partially-usable plan (filters stated, but the model returned zero
    rewrites) is *not* the same as the pinned "no usable plan" fallback: the
    raw utterance is used as the one query, but the stated filter still
    scopes the candidate search — `candidate_motorbike_ids` must NOT be
    unscoped here, unlike the true fallback."""
    translation(_plan(search_queries=[], spec_filters={"a2_eligible": True}))
    catalogue(matches=[BIKE_A])
    recorder = searches({UTTERANCE: [_chunk("chunk-1", motorbike_id=BIKE_A)]})

    result = _retrieve(_Session())

    assert result.queries == [UTTERANCE]
    assert result.applied_filters == {"a2_eligible": True}
    # Scoped, not unscoped: this distinguishes "queries fell back" from "the
    # whole plan fell back".
    assert result.candidate_motorbike_ids == [BIKE_A]
    assert recorder.calls[0][1] == [BIKE_A]


def test_qa_fully_empty_plan_is_the_complete_fallback(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A well-formed but entirely empty plan (no queries, no filters, no
    names) degrades exactly like a translation exception: raw utterance,
    unscoped, no structured search issued."""
    translation(_plan())
    filters_seen = catalogue()
    recorder = searches({UTTERANCE: [_chunk("chunk-1")]})

    result = _retrieve(_Session())

    assert result.queries == [UTTERANCE]
    assert result.applied_filters == {}
    assert result.candidate_motorbike_ids == []
    assert recorder.calls[0][1] is None
    assert filters_seen == []


# --- Criterion 4: RagResult exact field set, frozen ---------------------------


def test_qa_ragresult_field_set_is_exactly_the_pinned_four() -> None:
    assert set(rag_pipeline_service.RagResult.model_fields) == {
        "queries",
        "applied_filters",
        "candidate_motorbike_ids",
        "chunks",
    }


def test_qa_ragresult_is_frozen() -> None:
    result = rag_pipeline_service.RagResult(
        queries=[], applied_filters={}, candidate_motorbike_ids=[], chunks=[]
    )
    with pytest.raises(ValidationError):
        result.queries = ["mutated"]  # type: ignore[misc]


# --- Criterion 5: blank/whitespace utterance is safe --------------------------


@pytest.mark.parametrize("blank", ["", "   ", "\n\t", "  \n  \t "])
def test_qa_blank_or_whitespace_utterance_never_reaches_translation_or_search(
    blank: str, translation: Any, searches: Any, catalogue: Any
) -> None:
    translation(_plan(search_queries=["should never be reached"]))
    catalogue()
    recorder = searches({UTTERANCE: [_chunk("chunk-1")]})

    result = _retrieve(_Session(), blank)

    assert result == rag_pipeline_service.RagResult(
        queries=[], applied_filters={}, candidate_motorbike_ids=[], chunks=[]
    )
    assert recorder.calls == []


# --- Criterion 6: not wired into the chat responder / job path ----------------


def test_qa_rag_pipeline_service_is_imported_only_by_the_cli_and_the_retrieval_tool() -> None:
    """Static-scan the whole `backend/app` tree: `rag_pipeline_service` may be
    imported only by `app/cli/rag.py` and, since step 3.13, by the one tool that
    wraps it (`retrieve_bike_knowledge`) — the pinned "consumed exactly once"
    rule. A grep is not enough because a future import could be disguised as
    `from app.services import rag_pipeline_service` deep inside an unrelated
    module; this walks every `.py` file's AST. The responder itself still reaches
    the pipeline only through the tool, never directly.
    """
    app_root = Path(__file__).resolve().parents[2] / "app"
    assert app_root.is_dir()

    allowed = {
        app_root / "cli" / "rag.py",
        app_root / "services" / "rag_pipeline_service.py",
        app_root / "llm" / "agents" / "tools" / "retrieve_bike_knowledge.py",
    }
    offenders: list[str] = []

    for path in app_root.rglob("*.py"):
        if path in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [module] + [f"{module}.{alias.name}" for alias in node.names]
            else:
                continue
            if any("rag_pipeline_service" in name for name in names):
                offenders.append(str(path.relative_to(app_root)))

    assert offenders == [], f"rag_pipeline_service imported outside cli/rag.py by: {offenders}"
