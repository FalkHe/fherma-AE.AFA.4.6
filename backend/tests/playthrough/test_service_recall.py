"""WI1 (sprint 006/02): `service.recall` orders a run's whole narration by
meaning against a query, never a relevance floor, never a null-vector row,
across the whole run rather than whichever adventure is current (AC1, AC3).

`@pytest.mark.database`, same shared `playthrough_db` fixture every other
database-marked test in this suite uses -- pinned to `EMBEDDING_DIMENSIONS
="1536"` (`tests/playthrough/conftest.py`) to match `EMBEDDING_WIDTH`.
Narration rows are seeded with raw SQL and a literal vector, same pattern
as `test_event_embedding_round_trip.py`; only the query side goes through
`recall`, so `service.llm_service.embed_texts` is monkeypatched as a
module attribute, never a name import (AGENTS.md).

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio

import pytest
from sqlalchemy import text

from app.core.ids import generate_id
from app.core.llm.service import EmbeddingResult, Usage
from app.modules.playthrough import service
from app.modules.playthrough.models import EMBEDDING_WIDTH


def _vector(hot_index: int, value: float = 1.0, width: int = EMBEDDING_WIDTH) -> list[float]:
    """A vector of `width` zeros with `value` at `hot_index` -- one-hot-ish
    so cosine distance between any two of them is easy to reason about by
    hand."""
    vector = [0.0] * width
    vector[hot_index] = value
    return vector


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


async def _insert_campaign_run(session, run_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_runs (id, campaign_id, content_version) "
            "VALUES (:id, 'greenhollow', 'v1')"
        ),
        {"id": run_id},
    )


async def _insert_adventure_run(session, run_id: str, adventure_id: str, status: str) -> None:
    completed_at_clause = "now()" if status == "completed" else "NULL"
    await session.execute(
        text(
            "INSERT INTO adventure_runs (id, campaign_run_id, adventure_id, status, completed_at) "
            f"VALUES (:id, :run_id, :adventure_id, :status, {completed_at_clause})"
        ),
        {"id": generate_id(), "run_id": run_id, "adventure_id": adventure_id, "status": status},
    )


async def _insert_narration(
    session, run_id: str, *, text_value: str, vector: list[float] | None
) -> str:
    event_id = generate_id()
    if vector is None:
        await session.execute(
            text(
                "INSERT INTO events (id, campaign_run_id, type, visibility, payload) "
                "VALUES (:id, :run_id, 'narration', 'player', :payload)"
            ),
            {"id": event_id, "run_id": run_id, "payload": f'{{"text": "{text_value}"}}'},
        )
    else:
        await session.execute(
            text(
                "INSERT INTO events (id, campaign_run_id, type, visibility, payload, "
                "embedding, embedding_model) VALUES (:id, :run_id, 'narration', 'player', "
                ":payload, CAST(:embedding AS vector), 'test/embedding')"
            ),
            {
                "id": event_id,
                "run_id": run_id,
                "payload": f'{{"text": "{text_value}"}}',
                "embedding": _vector_literal(vector),
            },
        )
    return event_id


def _patch_embed_texts(monkeypatch, query_vector: list[float]) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_embed_texts(texts, *, model=None):
        calls.append(list(texts))
        return EmbeddingResult(
            vectors=[query_vector],
            usage=Usage(prompt_tokens=3, completion_tokens=0, total_tokens=3, cost_usd=0.0001),
        )

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    return calls


@pytest.mark.database
def test_ac1_the_closest_narration_line_is_returned_first(playthrough_db, monkeypatch):
    # <- AC1: a query vector nearer A than B returns A first.
    query_vector = _vector(0, value=0.9)
    query_vector[1] = 0.1
    calls = _patch_embed_texts(monkeypatch, query_vector)

    async def _scenario():
        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        near_id = await _insert_narration(
            playthrough_db, run_id, text_value="A goblin lunges from the dark.", vector=_vector(0)
        )
        far_id = await _insert_narration(
            playthrough_db, run_id, text_value="A merchant haggles over rope.", vector=_vector(1)
        )
        await playthrough_db.commit()

        results = await service.recall(playthrough_db, run_id=run_id, query="a goblin attacks")

        assert [r.id for r in results] == [near_id, far_id]
        assert results[0].text == "A goblin lunges from the dark."

    asyncio.run(_scenario())
    assert calls == [["a goblin attacks"]]


@pytest.mark.database
def test_ac1_a_line_from_an_earlier_adventure_of_the_same_run_wins_when_closest(
    playthrough_db, monkeypatch
):
    # <- AC1: recall spans the whole campaign run, not only whichever
    # adventure is currently active -- a closer line from an earlier,
    # completed adventure still comes first.
    query_vector = _vector(0, value=0.9)
    query_vector[1] = 0.1
    _patch_embed_texts(monkeypatch, query_vector)

    async def _scenario():
        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        await _insert_adventure_run(playthrough_db, run_id, "old-mine", "completed")
        await _insert_adventure_run(playthrough_db, run_id, "new-crypt", "active")

        earlier_id = await _insert_narration(
            playthrough_db,
            run_id,
            text_value="Deep in the old mine, a goblin lunges from the dark.",
            vector=_vector(0),
        )
        current_id = await _insert_narration(
            playthrough_db,
            run_id,
            text_value="In the new crypt, a merchant haggles over rope.",
            vector=_vector(1),
        )
        await playthrough_db.commit()

        results = await service.recall(playthrough_db, run_id=run_id, query="a goblin attacks")

        assert results[0].id == earlier_id
        assert [r.id for r in results] == [earlier_id, current_id]

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac1_a_row_with_a_null_vector_is_never_returned(playthrough_db, monkeypatch):
    # <- AC1: a narration row that failed to be encoded (null embedding)
    # is excluded even though it would otherwise fit within `k`.
    query_vector = _vector(0)
    _patch_embed_texts(monkeypatch, query_vector)

    async def _scenario():
        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        encoded_id = await _insert_narration(
            playthrough_db, run_id, text_value="A goblin lunges from the dark.", vector=_vector(0)
        )
        await _insert_narration(playthrough_db, run_id, text_value="Never encoded.", vector=None)
        await playthrough_db.commit()

        results = await service.recall(playthrough_db, run_id=run_id, query="a goblin", k=5)

        assert [r.id for r in results] == [encoded_id]
        assert all(r.text != "Never encoded." for r in results)

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac1_there_is_no_relevance_floor(playthrough_db, monkeypatch):
    # <- AC1: a line with almost no similarity to the query is still
    # returned within `k` -- nothing filters on distance itself.
    query_vector = _vector(0)
    _patch_embed_texts(monkeypatch, query_vector)

    async def _scenario():
        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        opposite_id = await _insert_narration(
            playthrough_db,
            run_id,
            text_value="Completely unrelated line.",
            vector=_vector(0, value=-1.0),
        )
        await playthrough_db.commit()

        results = await service.recall(playthrough_db, run_id=run_id, query="a goblin", k=5)

        assert [r.id for r in results] == [opposite_id]

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_recall_calls_embed_texts_exactly_once(playthrough_db, monkeypatch):
    # <- AC3: one embedding call regardless of how many narration rows
    # exist to compare against.
    query_vector = _vector(0)
    calls = _patch_embed_texts(monkeypatch, query_vector)

    async def _scenario():
        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        for index in range(3):
            await _insert_narration(
                playthrough_db, run_id, text_value=f"Line {index}.", vector=_vector(0)
            )
        await playthrough_db.commit()

        await service.recall(playthrough_db, run_id=run_id, query="a goblin", k=5)

    asyncio.run(_scenario())
    assert calls == [["a goblin"]]
