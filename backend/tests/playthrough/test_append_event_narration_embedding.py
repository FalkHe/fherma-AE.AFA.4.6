"""WI2 (sprint 006/01): narration is encoded as it is written, its
encoding billed onto that same line, and a failure to encode never reaches
the caller (AC2-AC4).

Engine-free, same `FakeSession` pattern as `test_append_event.py`.
`app.core.llm.service.embed_texts` is monkeypatched as a module attribute
on `app.modules.playthrough.service.llm_service`, per this sprint's
interface -- never a name import, since `append_event` itself calls it
that way.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from decimal import Decimal

import structlog.testing

from app.core.llm.service import EmbeddingResult, Usage
from app.modules.playthrough import service
from app.modules.playthrough.models import EMBEDDING_WIDTH


class FakeSession:
    """Engine-free stand-in for `AsyncSession` (`add`/`flush` only --
    `append_event` never queries or commits)."""

    def __init__(self):
        self.added: list[object] = []
        self.persisted: list[object] = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pending, self.added = self.added, []
        for obj in pending:
            if getattr(obj, "id", None) is None:
                obj.id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        self.persisted.extend(pending)


def _vector(width: int = EMBEDDING_WIDTH, value: float = 0.5) -> list[float]:
    return [value] * width


def test_ac2_narration_is_embedded_and_stores_vector_and_model(monkeypatch):
    calls = []

    def fake_embed_texts(texts, *, model=None):
        calls.append((list(texts), model))
        return EmbeddingResult(
            vectors=[_vector()],
            usage=Usage(prompt_tokens=7, completion_tokens=0, total_tokens=7, cost_usd=0.001),
        )

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "A goblin steps out of the shadows."},
        )
    )

    assert calls == [(["A goblin steps out of the shadows."], None)]
    assert event.embedding == _vector()
    assert event.embedding_model == service.get_settings().embedding_model


def test_ac2_embedding_usage_is_added_on_top_of_the_caller_s_usage(monkeypatch):
    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[_vector()],
            usage=Usage(prompt_tokens=7, completion_tokens=0, total_tokens=7, cost_usd=0.001),
        )

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeSession()
    caller_usage = Usage(prompt_tokens=100, completion_tokens=40, total_tokens=140, cost_usd=0.01)

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "A goblin steps out of the shadows."},
            usage=caller_usage,
        )
    )

    assert event.prompt_tokens == 107
    assert event.completion_tokens == 40
    assert event.cost_usd == Decimal("0.011")


def test_ac2_embedding_cost_alone_is_stored_when_caller_passes_no_usage(monkeypatch):
    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[_vector()],
            usage=Usage(prompt_tokens=7, completion_tokens=0, total_tokens=7, cost_usd=0.001),
        )

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "A goblin steps out of the shadows."},
        )
    )

    assert event.prompt_tokens == 7
    assert event.completion_tokens is None
    assert event.cost_usd == Decimal("0.001")


def test_ac2_cost_is_none_when_neither_side_reports_one(monkeypatch):
    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[_vector()],
            usage=Usage(prompt_tokens=7, completion_tokens=0, total_tokens=7, cost_usd=None),
        )

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "A goblin steps out of the shadows."},
        )
    )

    assert event.cost_usd is None


def test_ac3_blank_narration_is_not_embedded(monkeypatch):
    calls = []
    monkeypatch.setattr(
        service.llm_service,
        "embed_texts",
        lambda texts, **kw: calls.append(texts) or (_ for _ in ()).throw(AssertionError()),
    )
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db, run_id="run-1", type="narration", visibility="player", payload={"text": "   "}
        )
    )

    assert calls == []
    assert event.embedding is None
    assert event.embedding_model is None


def test_ac3_a_non_narration_type_is_never_embedded(monkeypatch):
    def boom(texts, *, model=None):
        raise AssertionError("embed_texts must not be called for a non-narration event")

    monkeypatch.setattr(service.llm_service, "embed_texts", boom)
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="player_action",
            visibility="player",
            payload={"text": "I draw my sword."},
        )
    )

    assert event.embedding is None
    assert event.embedding_model is None


def test_ac4_embedding_failure_still_writes_the_row_with_a_null_vector(monkeypatch):
    def fake_embed_texts(texts, *, model=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeSession()

    with structlog.testing.capture_logs() as logs:
        event = asyncio.run(
            service.append_event(
                db,
                run_id="run-1",
                type="narration",
                visibility="player",
                payload={"text": "A goblin steps out of the shadows."},
            )
        )

    assert event in db.persisted
    assert event.embedding is None
    assert event.embedding_model is None
    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["event"] == "narration_embedding_failed"
    assert warnings[0]["run_id"] == "run-1"
    assert warnings[0]["error"] == "boom"


def test_ac4_wrong_width_vector_still_writes_the_row_with_a_null_vector(monkeypatch):
    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[_vector(width=4)],
            usage=Usage(prompt_tokens=7, completion_tokens=0, total_tokens=7, cost_usd=None),
        )

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeSession()

    with structlog.testing.capture_logs() as logs:
        event = asyncio.run(
            service.append_event(
                db,
                run_id="run-1",
                type="narration",
                visibility="player",
                payload={"text": "A goblin steps out of the shadows."},
            )
        )

    assert event in db.persisted
    assert event.embedding is None
    assert event.embedding_model is None
    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["event"] == "narration_embedding_failed"


def test_ac4_failure_returns_the_same_event_the_success_path_would(monkeypatch):
    def fake_embed_texts(texts, *, model=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "hello"},
            turn_id="turn-1",
            actor_member_id="member-1",
        )
    )

    assert event.type == "narration"
    assert event.turn_id == "turn-1"
    assert event.actor_member_id == "member-1"
    assert event.payload == {"text": "hello"}
