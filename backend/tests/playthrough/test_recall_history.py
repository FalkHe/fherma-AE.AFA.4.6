"""WI2 (sprint 011/04): `service.recall_history` anchors on semantic
narration matches (`recall`, unchanged) and expands each anchor to its
turn's player-visible events (← research: I2).

`@pytest.mark.database`, same shared `playthrough_db` fixture the existing
recall suite uses, pinned to `EMBEDDING_DIMENSIONS="1536"`
(`tests/playthrough/conftest.py`). Narration rows are seeded with raw SQL
and a literal vector, same pattern as `test_service_recall.py`; only the
query side goes through `recall_history`, so `service.llm_service
.embed_texts` is monkeypatched as a module attribute, never a name import
(AGENTS.md).

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
    vector = [0.0] * width
    vector[hot_index] = value
    return vector


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vector) + "]"


def _patch_embed_texts(monkeypatch, query_vector: list[float]) -> None:
    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[query_vector],
            usage=Usage(prompt_tokens=3, completion_tokens=0, total_tokens=3, cost_usd=0.0001),
        )

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)


async def _insert_campaign_run(session, run_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_runs (id, campaign_id, content_version) "
            "VALUES (:id, 'greenhollow', 'v1')"
        ),
        {"id": run_id},
    )


async def _insert_member(session, run_id: str, user_id: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": user_id},
    )
    await session.execute(
        text(
            "INSERT INTO campaign_run_members (id, campaign_run_id, user_id, role) "
            "VALUES (:id, :run_id, :user_id, 'owner')"
        ),
        {"id": generate_id(), "run_id": run_id, "user_id": user_id},
    )


async def _insert_narration(
    session, run_id: str, *, text_value: str, vector: list[float], turn_id: str | None
) -> str:
    event_id = generate_id()
    await session.execute(
        text(
            "INSERT INTO events (id, campaign_run_id, type, visibility, turn_id, payload, "
            "embedding, embedding_model) VALUES (:id, :run_id, 'narration', 'player', "
            ":turn_id, :payload, CAST(:embedding AS vector), 'test/embedding')"
        ),
        {
            "id": event_id,
            "run_id": run_id,
            "turn_id": turn_id,
            "payload": f'{{"text": "{text_value}"}}',
            "embedding": _vector_literal(vector),
        },
    )
    return event_id


async def _insert_event(
    session, run_id: str, *, type_: str, visibility: str, turn_id: str | None, text_value: str
) -> str:
    event_id = generate_id()
    await session.execute(
        text(
            "INSERT INTO events (id, campaign_run_id, type, visibility, turn_id, payload) "
            "VALUES (:id, :run_id, :type, :visibility, :turn_id, :payload)"
        ),
        {
            "id": event_id,
            "run_id": run_id,
            "type": type_,
            "visibility": visibility,
            "turn_id": turn_id,
            "payload": f'{{"text": "{text_value}"}}',
        },
    )
    return event_id


@pytest.mark.database
def test_ac3_an_older_fact_returns_with_its_turns_player_visible_events(
    playthrough_db, monkeypatch
):
    # <- brief AC3: a query matching an older narration line, outside the
    # recent window, returns that turn's player action and narration
    # together.
    query_vector = _vector(0, value=0.9)
    query_vector[1] = 0.1
    _patch_embed_texts(monkeypatch, query_vector)

    async def _scenario():
        run_id = generate_id()
        user_id = generate_id()
        turn_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        await _insert_member(playthrough_db, run_id, user_id)

        action_id = await _insert_event(
            playthrough_db,
            run_id,
            type_="player_action",
            visibility="player",
            turn_id=turn_id,
            text_value="I search the old altar.",
        )
        narration_id = await _insert_narration(
            playthrough_db,
            run_id,
            text_value="Beneath the dust, a goblin lunges from the dark.",
            vector=_vector(0),
            turn_id=turn_id,
        )
        # A DM-only event on the same turn must never come back.
        await _insert_event(
            playthrough_db,
            run_id,
            type_="tool_call",
            visibility="dm",
            turn_id=turn_id,
            text_value="hidden bookkeeping",
        )
        # A newer, unrelated narration -- filler so the anchor is
        # unambiguously the older line.
        await _insert_narration(
            playthrough_db,
            run_id,
            text_value="A merchant haggles over rope.",
            vector=_vector(1),
            turn_id=None,
        )
        await playthrough_db.commit()

        results = await service.recall_history(
            playthrough_db, user_id=user_id, run_id=run_id, query="a goblin attacks"
        )

        assert results[0].turn_id == turn_id
        assert results[0].anchor_event_id == narration_id
        event_ids = {event.id for event in results[0].events}
        assert event_ids == {action_id, narration_id}

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_an_anchor_with_no_turn_returns_only_the_narration_row(playthrough_db, monkeypatch):
    # <- I2: an anchor whose event never carried a `turn_id` yields a
    # `RecalledTurn` holding only that narration row.
    query_vector = _vector(0)
    _patch_embed_texts(monkeypatch, query_vector)

    async def _scenario():
        run_id = generate_id()
        user_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        await _insert_member(playthrough_db, run_id, user_id)

        narration_id = await _insert_narration(
            playthrough_db,
            run_id,
            text_value="A goblin lunges from the dark.",
            vector=_vector(0),
            turn_id=None,
        )
        await playthrough_db.commit()

        results = await service.recall_history(
            playthrough_db, user_id=user_id, run_id=run_id, query="a goblin", limit=1
        )

        assert len(results) == 1
        assert results[0].turn_id is None
        assert results[0].anchor_event_id == narration_id
        assert [event.id for event in results[0].events] == [narration_id]

    asyncio.run(_scenario())
