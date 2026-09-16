"""WI1 (sprint 004/05, extended 004/06): `service.search_rules` -- embedding
a plain-words query through the shared gateway seam, matching it against
`srd_rules` by cosine distance, and dropping every match that falls under
`RELEVANCE_FLOOR` (AC2, AC3, AC4, AC5, AC6).

The empty-corpus behaviour is engine-free, mirroring
`test_service.py`'s `FakeScalarSession`: `require_corpus` only ever calls
`db.scalar(...)`, so a real database is not needed to prove it runs, and
fails, before `embed_texts` is ever reached. `embed_texts` is monkeypatched
as a module attribute on `app.core.llm.service`
(`srd_service.llm_service.embed_texts`), never a name import, per
`AGENTS.md`; a `FakeGateway` records whether it was called at all, which is
exactly what the empty-corpus assertion needs.

The ordering, limit, default-limit and relevance-floor behaviours need a
real cosine distance computed by Postgres, so they use the
`database`-marked `srd_db` fixture (`tests/srd/conftest.py`) with real,
synthetic 1536-wide rows rather than a faked ordering (per the work item:
"Search tests can populate a real corpus offline"). Basis vectors give a
query whose cosine similarity to each stored row is known exactly ahead of
time: a row identical to the query direction scores 1.0, a row at 45
degrees (`_diagonal`) scores ``1 / sqrt(2)`` (~0.707, above
`RELEVANCE_FLOOR`'s 0.40), and an orthogonal row (`_basis`, any index other
than the query's) scores 0.0 (below it) -- so every assertion is checked
against a real, computed value, not a hand-picked stand-in.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
is wrapped in a single `asyncio.run(...)`. `filterwarnings = ["error"]`
makes any warning fatal.
"""

import asyncio
import math

import pytest

from app.core.llm.service import EmbeddingResult, Usage
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdCorpusEmptyError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule

SQRT_HALF = 1 / math.sqrt(2)


class FakeScalarSession:
    """Stands in for `AsyncSession` for the engine-free empty-corpus test:
    `require_corpus` only ever calls `db.scalar(...)`, so this returns the
    queued value and nothing else needs to work."""

    def __init__(self, *values):
        self._values = list(values)

    async def scalar(self, _stmt):
        return self._values.pop(0)


class FakeGateway:
    """Stands in for `llm_service.embed_texts`: records whether -- and with
    what -- it was called, so the empty-corpus test can assert it is never
    reached (AC6), and the embedding-seam test can assert the query text
    actually went through it (AC5)."""

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
    """A unit basis vector along `index` in `EMBEDDING_WIDTH`-space -- one
    component `1.0`, every other `0.0`. Cosine similarity to `_basis(0)`
    (the query direction every test below uses) is 0.0 for any other
    `index` -- below `RELEVANCE_FLOOR`."""
    vector = [0.0] * EMBEDDING_WIDTH
    vector[index] = 1.0
    return vector


def _diagonal(index: int) -> list[float]:
    """A vector at 45 degrees off the query direction `_basis(0)`: `1.0` at
    position 0 *and* at `index` (`index` != 0), everywhere else `0.0`.
    Cosine similarity to `_basis(0)` is ``1 / sqrt(2)`` (~0.707) regardless
    of which `index` is used -- above `RELEVANCE_FLOOR`, and distinct rows
    (different `index`) can therefore share a score without sharing a
    heading."""
    vector = [0.0] * EMBEDDING_WIDTH
    vector[0] = 1.0
    vector[index] = 1.0
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


def test_ac6_empty_corpus_raises_before_any_gateway_call(monkeypatch):
    db = FakeScalarSession(0)
    gateway = FakeGateway()
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    with pytest.raises(SrdCorpusEmptyError):
        asyncio.run(srd_service.search_rules(db, "what is a fireball"))

    assert gateway.calls == []


def test_ac5_the_query_is_embedded_through_the_shared_gateway_seam(monkeypatch):
    db = FakeScalarSession(1)
    gateway = FakeGateway(vectors=[_basis(0)])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    # `db.execute` is never reached in this assertion's path of interest
    # (the corpus check already found a row); patch it to a no-op result so
    # this test stays engine-free while still proving the gateway saw the
    # query text.
    class _EmptyResult:
        def all(self):
            return []

    async def _fake_execute(_stmt):
        return _EmptyResult()

    db.execute = _fake_execute

    asyncio.run(srd_service.search_rules(db, "how does grappling work"))

    assert gateway.calls == [["how does grappling work"]]


@pytest.mark.database
def test_ac2_the_closest_passage_ranks_first_and_ordering_follows_similarity(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    identical = _row(
        heading_path="Spells › Fire Bolt",
        ordinal=0,
        text="identical direction",
        embedding=_basis(0),
    )
    diagonal = _row(
        heading_path="Spells › Ray of Frost",
        ordinal=0,
        text="45 degrees off",
        embedding=_diagonal(1),
    )
    # Below `RELEVANCE_FLOOR` (score 0.0) -- seeded to prove ordering still
    # holds for the rows that do come back, not to appear in the result
    # itself (that is `test_ac4_a_match_below_the_floor_is_absent...` below).
    orthogonal = _row(
        heading_path="Combat › Cover", ordinal=0, text="unrelated direction", embedding=_basis(2)
    )

    async def _seed():
        srd_db.add_all([orthogonal, diagonal, identical])
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=3))

    assert [match.heading_path for match in matches] == [
        "Spells › Fire Bolt",
        "Spells › Ray of Frost",
    ]
    assert matches[0].score == pytest.approx(1.0, abs=1e-6)
    assert matches[1].score == pytest.approx(SQRT_HALF, abs=1e-6)
    assert matches[0].ordinal == 0
    assert matches[0].text == "identical direction"


@pytest.mark.database
def test_ac3_limit_caps_how_many_matches_come_back(srd_db, monkeypatch):
    """All four rows score ~0.707 (above `RELEVANCE_FLOOR`), so this proves
    `limit` alone is what trims the four down to two -- the floor never
    even gets a chance to reject one here."""
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    rows = [
        _row(heading_path=f"Section {i}", ordinal=0, text=f"passage {i}", embedding=_diagonal(i))
        for i in range(1, 5)
    ]

    async def _seed():
        srd_db.add_all(rows)
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=2))

    assert len(matches) == 2
    assert all(match.score >= srd_service.RELEVANCE_FLOOR for match in matches)


@pytest.mark.database
def test_ac3_the_limit_defaults_when_omitted(srd_db, monkeypatch):
    """Every row scores ~0.707 (above `RELEVANCE_FLOOR`), so the returned
    count still comes from `DEFAULT_LIMIT`, not from the floor."""
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    rows = [
        _row(heading_path=f"Section {i}", ordinal=0, text=f"passage {i}", embedding=_diagonal(i))
        for i in range(1, srd_service.DEFAULT_LIMIT + 3)
    ]

    async def _seed():
        srd_db.add_all(rows)
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text"))

    assert len(matches) == srd_service.DEFAULT_LIMIT


def test_ac3_relevance_floor_is_a_pinned_module_constant():
    """AC3's code half: `RELEVANCE_FLOOR` lives beside `DEFAULT_LIMIT`, a
    plain module constant -- not read from settings/env, so this needs no
    fixture and no monkeypatch."""
    assert srd_service.RELEVANCE_FLOOR == 0.40


@pytest.mark.database
def test_ac4_a_match_below_the_floor_is_absent_from_the_result(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    kept = _row(
        heading_path="Spells › Fire Bolt",
        ordinal=0,
        text="identical direction",
        embedding=_basis(0),
    )
    dropped = _row(
        heading_path="Combat › Cover", ordinal=0, text="unrelated direction", embedding=_basis(1)
    )

    async def _seed():
        srd_db.add_all([kept, dropped])
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=2))

    assert [match.heading_path for match in matches] == ["Spells › Fire Bolt"]


@pytest.mark.database
def test_ac4_a_match_above_the_floor_is_kept(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    kept = _row(
        heading_path="Spells › Ray of Frost",
        ordinal=0,
        text="45 degrees off",
        embedding=_diagonal(1),
    )

    async def _seed():
        srd_db.add_all([kept])
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=1))

    assert [match.heading_path for match in matches] == ["Spells › Ray of Frost"]
    assert matches[0].score == pytest.approx(SQRT_HALF, abs=1e-6)


@pytest.mark.database
def test_ac4_every_match_below_the_floor_returns_an_empty_list(srd_db, monkeypatch):
    """A weak match is never a best effort (AC4): a query whose every
    candidate falls under `RELEVANCE_FLOOR` comes back empty, not with the
    closest-available guess."""
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    rows = [
        _row(heading_path=f"Section {i}", ordinal=0, text=f"passage {i}", embedding=_basis(i))
        for i in range(1, 4)
    ]

    async def _seed():
        srd_db.add_all(rows)
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=3))

    assert matches == []


@pytest.mark.database
def test_ac4_the_floor_is_applied_in_python_after_an_unfiltered_order_by_limit_query(
    srd_db, monkeypatch
):
    """The measured reason for AC4's implementation shape: a SQL `WHERE` on
    the distance defeats the HNSW plan (`Index Scan` 0.996 ms -> `Seq Scan`
    + `Sort` 8.475 ms), so the floor must be a Python-side filter on an
    otherwise unchanged `ORDER BY ... LIMIT` query -- proven here by
    capturing the actual statement handed to `db.execute` and asserting it
    still compiles to no `WHERE` at all, keeping the query the same shape
    that lets Postgres reach for the index."""
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    row = _row(
        heading_path="Spells › Fire Bolt",
        ordinal=0,
        text="identical direction",
        embedding=_basis(0),
    )

    async def _seed():
        srd_db.add_all([row])
        await srd_db.commit()

    asyncio.run(_seed())

    captured: dict[str, str] = {}
    original_execute = srd_db.execute

    async def _capturing_execute(stmt, *args, **kwargs):
        captured["sql"] = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        return await original_execute(stmt, *args, **kwargs)

    srd_db.execute = _capturing_execute

    asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=3))

    sql = captured["sql"].upper()
    assert "WHERE" not in sql
    assert "ORDER BY" in sql
    assert "LIMIT" in sql
