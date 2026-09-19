"""WI1: `append_event`, the only writer of `events` (AC1). Engine-free,
same `FakeSession` pattern as `test_service.py`, trimmed to what
`append_event` touches -- `add()` and `flush()`, no `execute()` since this
function runs no query.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from decimal import Decimal

import pytest

from app.core.llm.service import Usage
from app.modules.playthrough import service
from app.modules.playthrough.errors import InvalidEventPayloadError
from app.modules.playthrough.models import Event
from app.modules.playthrough.schemas import (
    AdventurePayload,
    NarrationPayload,
    NoticePayload,
    PlayerActionPayload,
    QuestionPayload,
    RollPayload,
    RollRequestedPayload,
    SceneEnteredPayload,
    ToolCallPayload,
)


class FakeSession:
    """Engine-free stand-in for `AsyncSession` (`add`/`flush` only --
    `append_event` never queries or commits)."""

    def __init__(self):
        self.added: list[object] = []
        self.persisted: list[object] = []
        self.committed = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pending, self.added = self.added, []
        for obj in pending:
            if getattr(obj, "id", None) is None:
                obj.id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        self.persisted.extend(pending)

    async def commit(self):
        self.committed += 1


VALID_PAYLOADS: dict[str, dict] = {
    "narration": {"text": "A goblin steps out of the shadows."},
    "player_action": {"text": "I draw my sword."},
    "roll_requested": {
        "kind": "attack",
        "actor_id": "obj-1",
        "formula": "1d20+3",
        "context": {"target_id": "obj-2"},
    },
    "roll": {
        "kind": "attack",
        "actor_id": "obj-1",
        "formula": "1d20+3",
        "faces": [15],
        "modifier": 3,
        "total": 18,
    },
    "question": {"text": "Which way?", "options": ["left", "right"]},
    "tool_call": {
        "name": "attack",
        "args": {"target_id": "obj-2"},
        "roll_ids": ["roll-1"],
        "result": "ok",
        "outcome": {"hit": True},
    },
    "scene_entered": {"adventure_run_id": "adv-1", "scene_id": "scene-1"},
    "adventure_started": {"adventure_run_id": "adv-1"},
    "adventure_completed": {"adventure_run_id": "adv-1"},
    "system": {"message": "The DM pauses the scene."},
    "error": {"message": "That action is not available here."},
    "warning": {"message": "Low on time."},
}


@pytest.mark.parametrize("event_type", sorted(VALID_PAYLOADS))
def test_accepts_and_stores_each_of_the_twelve_types(event_type):
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type=event_type,
            visibility="player",
            payload=VALID_PAYLOADS[event_type],
        )
    )

    assert isinstance(event, Event)
    assert event.type == event_type
    assert event.campaign_run_id == "run-1"
    assert db.added == []  # flushed, not left pending
    assert event in db.persisted


def test_accepts_the_type_s_own_model_instance_directly():
    db = FakeSession()
    payload = NarrationPayload(text="Rain begins to fall.")

    event = asyncio.run(
        service.append_event(
            db, run_id="run-1", type="narration", visibility="player", payload=payload
        )
    )

    assert event.payload == {"text": "Rain begins to fall."}


def test_stores_payload_camel_case():
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="player_action",
            visibility="player",
            payload={"text": "I look around.", "answers_question_id": "evt-1"},
        )
    )

    assert event.payload == {"text": "I look around.", "answersQuestionId": "evt-1"}


def test_unknown_type_is_refused_and_writes_nothing():
    db = FakeSession()

    with pytest.raises(InvalidEventPayloadError):
        asyncio.run(
            service.append_event(
                db, run_id="run-1", type="not_a_type", visibility="player", payload={}
            )
        )

    assert db.added == []
    assert db.persisted == []


def test_unknown_visibility_is_refused_and_writes_nothing():
    db = FakeSession()

    with pytest.raises(InvalidEventPayloadError):
        asyncio.run(
            service.append_event(
                db,
                run_id="run-1",
                type="narration",
                visibility="dungeon_master",
                payload={"text": "Hi"},
            )
        )

    assert db.added == []
    assert db.persisted == []


def test_payload_missing_a_required_field_is_refused_and_writes_nothing():
    db = FakeSession()

    with pytest.raises(InvalidEventPayloadError):
        asyncio.run(
            service.append_event(
                db, run_id="run-1", type="narration", visibility="player", payload={}
            )
        )

    assert db.added == []
    assert db.persisted == []


def test_payload_with_an_unexpected_field_is_refused_and_writes_nothing():
    db = FakeSession()

    with pytest.raises(InvalidEventPayloadError):
        asyncio.run(
            service.append_event(
                db,
                run_id="run-1",
                type="roll",
                visibility="player",
                payload={**VALID_PAYLOADS["roll"], "bogus_field": True},
            )
        )

    assert db.added == []
    assert db.persisted == []


def test_payload_shaped_for_a_different_type_is_refused_and_writes_nothing():
    db = FakeSession()

    with pytest.raises(InvalidEventPayloadError):
        asyncio.run(
            service.append_event(
                db,
                run_id="run-1",
                type="roll",
                visibility="player",
                payload=NarrationPayload(text="wrong shape"),
            )
        )

    assert db.added == []
    assert db.persisted == []


def test_never_commits_the_caller_owns_the_transaction():
    db = FakeSession()

    asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "hello"},
        )
    )

    assert db.committed == 0


def test_carries_turn_id_and_actor_member_id_through_unchanged():
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

    assert event.turn_id == "turn-1"
    assert event.actor_member_id == "member-1"


def test_usage_tokens_copy_across_and_cost_is_an_exact_decimal():
    db = FakeSession()
    usage = Usage(prompt_tokens=120, completion_tokens=30, total_tokens=150, cost_usd=0.1)

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "hello"},
            usage=usage,
        )
    )

    assert event.prompt_tokens == 120
    assert event.completion_tokens == 30
    assert event.cost_usd == Decimal("0.1")
    assert event.cost_usd != Decimal(0.1)  # the float-repr trap this guards against


def test_usage_with_no_cost_leaves_cost_null():
    db = FakeSession()
    usage = Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15, cost_usd=None)

    event = asyncio.run(
        service.append_event(
            db,
            run_id="run-1",
            type="narration",
            visibility="player",
            payload={"text": "hello"},
            usage=usage,
        )
    )

    assert event.prompt_tokens == 10
    assert event.cost_usd is None


def test_no_usage_leaves_tokens_and_cost_null():
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db, run_id="run-1", type="narration", visibility="player", payload={"text": "hi"}
        )
    )

    assert event.prompt_tokens is None
    assert event.completion_tokens is None
    assert event.cost_usd is None


@pytest.mark.parametrize(
    "model_cls,payload",
    [
        (AdventurePayload, {"adventure_run_id": "adv-1"}),
        (QuestionPayload, {"text": "Which way?", "options": []}),
        (RollRequestedPayload, VALID_PAYLOADS["roll_requested"]),
        (RollPayload, VALID_PAYLOADS["roll"]),
        (SceneEnteredPayload, VALID_PAYLOADS["scene_entered"]),
        (ToolCallPayload, VALID_PAYLOADS["tool_call"]),
        (PlayerActionPayload, {"text": "I run."}),
        (NoticePayload, {"message": "note"}),
    ],
)
def test_payload_models_round_trip_their_own_valid_dict(model_cls, payload):
    assert model_cls.model_validate(payload).model_dump(by_alias=True)
