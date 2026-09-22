"""WI1 (sprint 004/05): `service.search_rules` -- embedding a plain-words
query through the shared gateway seam and matching it against `srd_rules`
by cosine distance.

The empty-corpus and gateway-seam behaviours are engine-free, mirroring
`test_service.py`'s `FakeScalarSession`: `require_corpus` only ever calls
`db.scalar(...)`, so a real database is not needed to prove a call runs,
and fails, before `embed_texts` is ever reached (AC6). `embed_texts` is
monkeypatched as a module attribute on `app.core.llm.service`
(`srd_service.llm_service.embed_texts`), never a name import, per
`AGENTS.md`.

Ordering, limit and score values need a real cosine distance computed by
Postgres, so those use the `database`-marked `srd_db` fixture
(`tests/srd/conftest.py`) with synthetic 1536-wide basis-vector rows: a row
identical to the query direction has distance `0.0`, an orthogonal row has
distance `1.0` -- known exactly ahead of time, so the assertion is checked
against a real, computed value.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
is wrapped in a single `asyncio.run(...)`."""

import asyncio

import pytest

from app.core.llm.service import EmbeddingResult, Usage
from app.core.settings import get_settings
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdCorpusEmptyError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule


@pytest.fixture(autouse=True)
def embedding_width(monkeypatch):
    """Pins `EMBEDDING_DIMENSIONS` to `EMBEDDING_WIDTH` for every test in
    this module, so `check_vector_width()` (run first by `search_rules`)
    passes without a real, migrated database -- the suite-wide pin in
    `tests/conftest.py` (width 4) never matches on its own."""
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_WIDTH))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeScalarSession:
    """Stands in for `AsyncSession` for the engine-free tests:
    `require_corpus` only ever calls `db.scalar(...)`."""

    def __init__(self, *values):
        self._values = list(values)
        self.execute_calls: list[object] = []

    async def scalar(self, _stmt):
        return self._values.pop(0)

    async def execute(self, stmt):
        self.execute_calls.append(stmt)

        class _EmptyResult:
            def all(self):
                return []

        return _EmptyResult()


class FakeGateway:
    """Stands in for `llm_service.embed_texts`: records what it was called
    with, so the empty-corpus test can assert it is never reached and the
    embedding-seam test can assert the query text actually went through
    it."""

    def __init__(self, *, vectors: list[list[float]] | None = None):
        self._vectors = vectors
        self.calls: list[list[str]] = []

    def __call__(self, texts, *, model=None):
        self.calls.append(list(texts))
        vectors = (
            self._vectors if self._vectors is not None else [[0.0] * EMBEDDING_WIDTH] * len(texts)
        )
        return EmbeddingResult(
            vectors=vectors,
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.01),
        )


def _basis(index: int) -> list[float]:
    vector = [0.0] * EMBEDDING_WIDTH
    vector[index] = 1.0
    return vector


def _skewed(other_index: int, weight: float) -> list[float]:
    """A vector at a known, sub-`RELEVANCE_FLOOR` cosine distance from
    `_basis(0)`: `weight` controls how far, without ever reaching an
    orthogonal (distance `1.0`) vector, which the floor now drops."""
    vector = [0.0] * EMBEDDING_WIDTH
    vector[0] = 1.0
    vector[other_index] = weight
    return vector


def _row(*, heading_path: str, ordinal: int, text: str, embedding: list[float]) -> SrdRule:
    return SrdRule(
        source_version="v1",
        heading_path=heading_path,
        ordinal=ordinal,
        text=text,
        token_count=3,
        embedding_model="test/embedding-model",
        embedding=embedding,
    )


def test_empty_corpus_raises_before_any_gateway_call(monkeypatch):
    db = FakeScalarSession(0)
    gateway = FakeGateway()
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    with pytest.raises(SrdCorpusEmptyError):
        asyncio.run(srd_service.search_rules(db, "what is a fireball"))

    assert gateway.calls == []


def test_the_query_text_reaches_embed_texts(monkeypatch):
    db = FakeScalarSession(1)
    gateway = FakeGateway(vectors=[_basis(0)])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    asyncio.run(srd_service.search_rules(db, "how does grappling work"))

    assert gateway.calls == [["how does grappling work"]]


def test_default_limit_lands_in_the_statement(monkeypatch):
    db = FakeScalarSession(1)
    gateway = FakeGateway(vectors=[_basis(0)])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    asyncio.run(srd_service.search_rules(db, "how does grappling work"))

    assert db.execute_calls[0]._limit_clause.value == srd_service.DEFAULT_LIMIT


def test_explicit_limit_is_honoured(monkeypatch):
    db = FakeScalarSession(1)
    gateway = FakeGateway(vectors=[_basis(0)])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    asyncio.run(srd_service.search_rules(db, "how does grappling work", limit=2))

    assert db.execute_calls[0]._limit_clause.value == 2


@pytest.mark.database
def test_the_closest_passage_ranks_first_and_score_is_the_raw_distance(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    identical = _row(
        heading_path="Spells › Fire Bolt",
        ordinal=0,
        text="identical direction",
        embedding=_basis(0),
    )
    near_one = _row(
        heading_path="Combat › Cover",
        ordinal=0,
        text="a further-but-still-relevant direction",
        embedding=_skewed(1, 1.0),
    )
    near_two = _row(
        heading_path="Conditions › Frightened",
        ordinal=0,
        text="the furthest-but-still-relevant direction",
        embedding=_skewed(2, 2.0),
    )

    async def _seed():
        srd_db.add_all([near_one, near_two, identical])
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=3))

    assert matches[0].heading_path == "Spells › Fire Bolt"
    assert matches[0].score == pytest.approx(0.0, abs=1e-6)
    assert matches[1].score == pytest.approx(1 - 1 / (2**0.5), abs=1e-6)
    assert matches[2].score == pytest.approx(1 - 1 / (5**0.5), abs=1e-6)


def test_rows_past_the_floor_are_dropped_rows_at_or_below_it_are_kept_in_order(monkeypatch):
    db = FakeScalarSession(1)
    gateway = FakeGateway(vectors=[_basis(0)])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    class _FixedDistanceResult:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    async def execute(_stmt):
        return _FixedDistanceResult(
            [
                ("Combat › Cover", 0, "closest", 0.1),
                (
                    "Using Ability Scores › Saving Throws",
                    0,
                    "at the floor",
                    srd_service.RELEVANCE_FLOOR,
                ),
                ("Spell Lists › Fireball", 0, "past the floor", srd_service.RELEVANCE_FLOOR + 0.01),
            ]
        )

    db.execute = execute

    matches = asyncio.run(srd_service.search_rules(db, "irrelevant query text"))

    assert [match.heading_path for match in matches] == [
        "Combat › Cover",
        "Using Ability Scores › Saving Throws",
    ]


def test_a_result_of_only_above_floor_rows_returns_empty_list(monkeypatch):
    db = FakeScalarSession(1)
    gateway = FakeGateway(vectors=[_basis(0)])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    class _FixedDistanceResult:
        def all(self):
            return [
                ("Spell Lists › Fireball", 0, "past the floor", srd_service.RELEVANCE_FLOOR + 0.01)
            ]

    async def execute(_stmt):
        return _FixedDistanceResult()

    db.execute = execute

    matches = asyncio.run(srd_service.search_rules(db, "irrelevant query text"))

    assert matches == []


@pytest.mark.database
def test_a_row_above_the_relevance_floor_is_filtered_a_row_at_it_is_kept(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    identical = _row(
        heading_path="Spells › Fire Bolt",
        ordinal=0,
        text="identical direction",
        embedding=_basis(0),
    )
    orthogonal = _row(
        heading_path="Combat › Cover", ordinal=0, text="unrelated direction", embedding=_basis(1)
    )

    async def _seed():
        srd_db.add_all([orthogonal, identical])
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=2))

    assert [match.heading_path for match in matches] == ["Spells › Fire Bolt"]
    assert matches[0].score == pytest.approx(0.0, abs=1e-6)


@pytest.mark.database
def test_limit_caps_how_many_matches_come_back(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    rows = [
        _row(
            heading_path=f"Section {i}",
            ordinal=0,
            text=f"passage {i}",
            embedding=_basis(0) if i == 0 else _skewed(i, float(i)),
        )
        for i in range(4)
    ]

    async def _seed():
        srd_db.add_all(rows)
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=2))

    assert len(matches) == 2
