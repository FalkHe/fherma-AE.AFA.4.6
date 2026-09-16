"""WI1 (sprint 004/05): `service.search_rules` -- embedding a plain-words
query through the shared gateway seam and matching it against `srd_rules`
by cosine distance (AC2, AC3, AC5, AC6).

The empty-corpus behaviour is engine-free, mirroring
`test_service.py`'s `FakeScalarSession`: `require_corpus` only ever calls
`db.scalar(...)`, so a real database is not needed to prove it runs, and
fails, before `embed_texts` is ever reached. `embed_texts` is monkeypatched
as a module attribute on `app.core.llm.service`
(`srd_service.llm_service.embed_texts`), never a name import, per
`AGENTS.md`; a `FakeGateway` records whether it was called at all, which is
exactly what the empty-corpus assertion needs.

The ordering, limit and default-limit behaviours need a real cosine
distance computed by Postgres, so they use the `database`-marked `srd_db`
fixture (`tests/srd/conftest.py`) with real, synthetic 1536-wide rows
rather than a faked ordering (per the work item: "Search tests can populate
a real corpus offline"). Three orthogonal-ish basis vectors give a query
whose cosine similarity to each stored row is known exactly ahead of time:
a row identical to the query direction scores 1.0, a row at 45 degrees
scores ``1 / sqrt(2)``, and an orthogonal row scores 0.0 -- so the ordering
assertion is checked against a real, computed value, not a hand-picked
stand-in.

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
    component `1.0`, every other `0.0`."""
    vector = [0.0] * EMBEDDING_WIDTH
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
        embedding=[1.0, 1.0] + [0.0] * (EMBEDDING_WIDTH - 2),
    )
    orthogonal = _row(
        heading_path="Combat › Cover", ordinal=0, text="unrelated direction", embedding=_basis(1)
    )

    async def _seed():
        srd_db.add_all([orthogonal, diagonal, identical])
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=3))

    assert [match.heading_path for match in matches] == [
        "Spells › Fire Bolt",
        "Spells › Ray of Frost",
        "Combat › Cover",
    ]
    assert matches[0].score == pytest.approx(1.0, abs=1e-6)
    assert matches[1].score == pytest.approx(SQRT_HALF, abs=1e-6)
    assert matches[2].score == pytest.approx(0.0, abs=1e-6)
    assert matches[0].ordinal == 0
    assert matches[0].text == "identical direction"


@pytest.mark.database
def test_ac3_limit_caps_how_many_matches_come_back(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    rows = [
        _row(heading_path=f"Section {i}", ordinal=0, text=f"passage {i}", embedding=_basis(i))
        for i in range(4)
    ]

    async def _seed():
        srd_db.add_all(rows)
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text", limit=2))

    assert len(matches) == 2


@pytest.mark.database
def test_ac3_the_limit_defaults_when_omitted(srd_db, monkeypatch):
    query_vector = _basis(0)
    gateway = FakeGateway(vectors=[query_vector])
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", gateway)

    rows = [
        _row(heading_path=f"Section {i}", ordinal=0, text=f"passage {i}", embedding=_basis(i))
        for i in range(srd_service.DEFAULT_LIMIT + 2)
    ]

    async def _seed():
        srd_db.add_all(rows)
        await srd_db.commit()

    asyncio.run(_seed())

    matches = asyncio.run(srd_service.search_rules(srd_db, "irrelevant query text"))

    assert len(matches) == srd_service.DEFAULT_LIMIT
