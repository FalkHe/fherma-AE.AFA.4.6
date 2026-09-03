"""`app/services/rag_pipeline_service.py` — the pipeline's own three decisions.

Translation, hybrid search and the spec filter each have their own test module
(and their own live proof); what this module covers is the orchestration nobody
else can see:

* **cross-query fusion and dedup** — a chunk two queries found must outrank one
  a single query found, the surviving copy carries the fused score, and equal
  scores break on the chunk id;
* **candidate scoping** — derived filters and named bikes become one candidate
  list, and *every* query is searched inside it (nothing derived ⇒ unscoped);
* **the pinned fallback** — a malformed or unusable translation degrades to the
  raw utterance with no filters instead of raising.

No test reaches OpenRouter or a database: the translation chain, the two
services the pipeline composes and the name lookup are all stubbed, and the
"session" is an inert marker — the pipeline itself issues no statement.
"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pytest

from app.core.config import get_settings
from app.db.models.motorbike import MotorbikeStatus
from app.llm import query_translation
from app.llm.query_translation import SpecFilters, TranslatedQuery
from app.services import catalogue_search_service, product_service, rag_pipeline_service
from app.services.retrieval_service import RetrievedChunk

UTTERANCE = "I'm 1.65 m, just got my A2, mostly city commuting"
NAMED_BIKE = "Honda CB500F"
BIKE_A = "01J0BIKE0000000000000000AA"
BIKE_B = "01J0BIKE0000000000000000BB"
BIKE_C = "01J0BIKE0000000000000000CC"


class _Session:
    """Marker object: the pipeline passes it on and never executes anything."""


@dataclass(frozen=True, slots=True)
class _Motorbike:
    """The two attributes the pipeline reads off a resolved catalogue entry."""

    id: str
    status: MotorbikeStatus


class _Searches:
    """Records every `retrieval_service.search` call and replays scripted rows."""

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

    @property
    def queries(self) -> list[str]:
        return [call[0] for call in self.calls]


def _chunk(chunk_id: str, *, motorbike_id: str = BIKE_A, score: float = 0.03) -> RetrievedChunk:
    """One retrieved chunk with plausible provenance."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        motorbike_id=motorbike_id,
        text=f"Prose {chunk_id}.",
        score=score,
        source_document_id="01J0DOC00000000000000000AA",
        source_url="https://example.test/review",
        source_title="Commuter review",
        heading_path="Honda CB500F > Comfort",
        page_number=None,
        sequence=3,
    )


def _plan(**values: Any) -> TranslatedQuery:
    """Build a translation result the way the structured output would arrive."""
    return TranslatedQuery.model_validate(values)


@pytest.fixture
def translation(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace the translation chain, so no test reaches OpenRouter.

    Returns a setter taking either the plan the "model" answers with or an
    exception it raises (a malformed answer is what the structured-output parser
    turns into an exception).
    """
    prompts: list[str] = []

    def install(answer: TranslatedQuery | Exception) -> list[str]:
        class _Chain:
            async def ainvoke(self, messages: Any) -> TranslatedQuery:
                prompts.append(messages[0].content)
                if isinstance(answer, Exception):
                    raise answer
                return answer

        monkeypatch.setattr(
            query_translation, "build_translation_chain", lambda model=None: _Chain()
        )
        return prompts

    return install


@pytest.fixture
def searches(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace `retrieval_service.search` with a recording stub."""

    def install(rankings: dict[str, list[RetrievedChunk]] | None = None) -> _Searches:
        recorder = _Searches(rankings)
        monkeypatch.setattr(
            rag_pipeline_service.retrieval_service, "search", recorder.search, raising=True
        )
        return recorder

    return install


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Replace the structured search and the name lookup with recording stubs."""

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
    """Drive the async pipeline from a synchronous test."""
    return asyncio.run(rag_pipeline_service.retrieve(session, utterance, **kwargs))


# --- cross-query fusion -------------------------------------------------------


def test_fusion_ranks_a_chunk_two_queries_found_first(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """The second RRF pass, dedup included: `1 / (RRF_K + rank)` summed per chunk.

    Query A's own ranking is seeded descending, so a pipeline that merely
    concatenated the two lists (or trusted the per-query scores) would keep
    `chunk-1` first and fail here.
    """
    translation(_plan(search_queries=["a2 commuter naked", "low seat height city"]))
    catalogue()
    recorder = searches(
        {
            "a2 commuter naked": [_chunk("chunk-1"), _chunk("chunk-2"), _chunk("chunk-3")],
            "low seat height city": [_chunk("chunk-2"), _chunk("chunk-4")],
        }
    )

    result = _retrieve(_Session())

    rrf_k = get_settings().rrf_k
    assert [chunk.chunk_id for chunk in result.chunks] == [
        "chunk-2",  # rank 2 + rank 1
        "chunk-1",  # rank 1
        "chunk-4",  # rank 2
        "chunk-3",  # rank 3
    ]
    assert result.chunks[0].score == pytest.approx(1 / (rrf_k + 2) + 1 / (rrf_k + 1))
    assert result.chunks[1].score == pytest.approx(1 / (rrf_k + 1))
    # Every query was searched, and the queries are the translation's.
    assert recorder.queries == result.queries == ["a2 commuter naked", "low seat height city"]


def test_the_deduplicated_copy_keeps_its_provenance(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Only the score is replaced; the citation fields survive the fusion."""
    translation(_plan(search_queries=["seat height", "commuting"]))
    catalogue()
    original = _chunk("chunk-1", motorbike_id=BIKE_B)
    searches({"seat height": [original], "commuting": [original]})

    (chunk,) = _retrieve(_Session()).chunks

    assert chunk.model_dump(exclude={"score"}) == original.model_dump(exclude={"score"})
    assert chunk.score != original.score


def test_equal_scores_break_on_the_chunk_id(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Two chunks found at the same rank by one query each order by id."""
    translation(_plan(search_queries=["first", "second"]))
    catalogue()
    searches({"first": [_chunk("chunk-z")], "second": [_chunk("chunk-a")]})

    result = _retrieve(_Session())

    assert [chunk.chunk_id for chunk in result.chunks] == ["chunk-a", "chunk-z"]
    assert result.chunks[0].score == pytest.approx(result.chunks[1].score)


def test_the_fused_list_is_cut_to_the_limit(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """`limit` bounds both what each query retrieves and what comes back."""
    translation(_plan(search_queries=["a", "b"]))
    catalogue()
    recorder = searches(
        {
            "a": [_chunk("chunk-1"), _chunk("chunk-2")],
            "b": [_chunk("chunk-3"), _chunk("chunk-4")],
        }
    )

    result = _retrieve(_Session(), limit=2)

    assert len(result.chunks) == 2
    assert [call[2] for call in recorder.calls] == [2, 2]


# --- candidate scoping --------------------------------------------------------


def test_filters_and_named_bikes_become_one_scoped_search_space(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """Named bikes first, then the filter matches; every query sees that list."""
    translation(
        _plan(
            search_queries=["a2 commuter", "low seat"],
            spec_filters={"a2_eligible": True, "seat_height_mm_max": 800},
            target_motorbike_names=[NAMED_BIKE],
        )
    )
    filters_seen = catalogue(
        matches=[BIKE_B, BIKE_A],
        by_slug={"honda-cb500f": _Motorbike(BIKE_C, MotorbikeStatus.APPROVED)},
    )
    recorder = searches({"a2 commuter": [_chunk("chunk-1", motorbike_id=BIKE_C)]})

    result = _retrieve(_Session())

    assert result.candidate_motorbike_ids == [BIKE_C, BIKE_B, BIKE_A]
    assert result.applied_filters == {"a2_eligible": True, "seat_height_mm_max": 800}
    # The structured half got the translated filters, unchanged...
    assert [filters.values()["seat_height_mm_max"] for filters in filters_seen] == [800]
    # ...and both legs of the prose half were scoped to the merged shortlist.
    assert [call[1] for call in recorder.calls] == [[BIKE_C, BIKE_B, BIKE_A]] * 2


def test_nothing_derived_searches_the_whole_catalogue(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """No filters and no resolvable name ⇒ `motorbike_ids=None`, not `[]`.

    An unresolvable name is skipped rather than turned into an empty search
    space, which would silently answer every question with nothing.
    """
    translation(_plan(search_queries=["touring comfort"], target_motorbike_names=["Bikeley 999"]))
    catalogue()
    recorder = searches({"touring comfort": [_chunk("chunk-1")]})

    result = _retrieve(_Session())

    assert result.candidate_motorbike_ids == []
    assert result.applied_filters == {}
    assert [call[1] for call in recorder.calls] == [None]
    assert len(result.chunks) == 1


def test_an_unapproved_named_bike_is_not_a_candidate(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A backlog entry has no reviewed prose, so its name resolves to nothing."""
    translation(_plan(search_queries=["reliability"], target_motorbike_names=[NAMED_BIKE]))
    catalogue(by_slug={"honda-cb500f": _Motorbike(BIKE_C, MotorbikeStatus.BACKLOG)})
    recorder = searches()

    assert _retrieve(_Session()).candidate_motorbike_ids == []
    assert [call[1] for call in recorder.calls] == [None]


def test_constraints_matching_nothing_return_no_chunks(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A shortlist of zero is answered honestly, not by widening the search.

    Searching unscoped here would surface prose about bikes the customer's hard
    constraint ruled out; `applied_filters` plus an empty candidate list is what
    tells the agent which claim emptied the catalogue.
    """
    translation(_plan(search_queries=["a2 commuter"], spec_filters={"a2_eligible": True}))
    catalogue(matches=[])
    recorder = searches({"a2 commuter": [_chunk("chunk-1")]})

    result = _retrieve(_Session())

    assert result.chunks == []
    assert result.candidate_motorbike_ids == []
    assert result.applied_filters == {"a2_eligible": True}
    assert recorder.calls == []


# --- the pinned fallback ------------------------------------------------------


def test_a_malformed_translation_falls_back_to_the_raw_utterance(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """The pinned fallback: raw utterance, no filters, whole catalogue, no raise."""
    translation(ValueError("Received a malformed answer from the model."))
    filters_seen = catalogue(matches=[BIKE_A])
    recorder = searches({UTTERANCE: [_chunk("chunk-1")]})

    result = _retrieve(_Session())

    assert result.queries == [UTTERANCE]
    assert result.applied_filters == {}
    assert result.candidate_motorbike_ids == []
    assert [chunk.chunk_id for chunk in result.chunks] == ["chunk-1"]
    assert [call[1] for call in recorder.calls] == [None]
    # The structured half is not consulted without a plan.
    assert filters_seen == []


def test_a_translation_without_usable_output_falls_back_too(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """A well-formed but empty plan is the same fallback: nothing to work with."""
    translation(_plan())
    catalogue()
    recorder = searches({UTTERANCE: [_chunk("chunk-1")]})

    result = _retrieve(_Session())

    assert result.queries == [UTTERANCE]
    assert result.applied_filters == {}
    assert [call[1] for call in recorder.calls] == [None]
    assert len(result.chunks) == 1


def test_a_blank_utterance_costs_nothing(translation: Any, searches: Any, catalogue: Any) -> None:
    """No translation, no search, no gateway call — an empty result."""
    prompts = translation(_plan(search_queries=["never asked"]))
    catalogue()
    recorder = searches({UTTERANCE: [_chunk("chunk-1")]})

    result = _retrieve(_Session(), "   \n ")

    assert result == rag_pipeline_service.RagResult(
        queries=[], applied_filters={}, candidate_motorbike_ids=[], chunks=[]
    )
    assert prompts == []
    assert recorder.calls == []


def test_the_utterance_and_the_history_reach_the_translation(
    translation: Any, searches: Any, catalogue: Any
) -> None:
    """The prompt carries the customer's words, the recap and the preferences."""
    prompts = translation(_plan(search_queries=["a2 commuter"]))
    catalogue()
    searches()

    _retrieve(
        _Session(),
        history_summary="The customer commutes 20 km each way.",
        preferences=[
            query_translation.ActivePreference(attribute="licence", value="A2", firmness="hard")
        ],
    )

    assert len(prompts) == 1
    assert UTTERANCE in prompts[0]
    assert "The customer commutes 20 km each way." in prompts[0]
    assert "A2" in prompts[0]
