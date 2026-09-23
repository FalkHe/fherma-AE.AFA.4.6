"""WI1: `append_event`, the only writer of `events` (AC1), now validating
against all sixteen registered types -- the twelve settled in intent 005
plus `item_moved`, `hp_changed`, `way_opened` and `rule_looked_up`, added
in sprint 010/04. Engine-free, same `FakeSession` pattern as
`test_service.py`, trimmed to what `append_event` touches -- `add()` and
`flush()`, no `execute()` since this function runs no query.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from decimal import Decimal

import pytest

from app.core.llm.service import EmbeddingResult, Usage
from app.modules.playthrough import service
from app.modules.playthrough.errors import InvalidEventPayloadError
from app.modules.playthrough.models import EMBEDDING_WIDTH, Event
from app.modules.playthrough.schemas import (
    AdventurePayload,
    HpChangedPayload,
    ItemMovedPayload,
    NarrationPayload,
    NoticePayload,
    PlayerActionPayload,
    QuestionPayload,
    RollPayload,
    RollRequestedPayload,
    RuleLookedUpPayload,
    SceneEnteredPayload,
    ToolCallPayload,
    WayOpenedPayload,
)


@pytest.fixture(autouse=True)
def _stub_embed_texts(monkeypatch):
    """WI2 (sprint 006/01): `append_event` now embeds every narration
    through `llm_service.embed_texts` before it writes the row. This
    file's tests are about AC1, not that embedding (see
    `test_append_event_narration_embedding.py` for AC2-4) -- stubbed here
    with a zero-cost, right-width vector so no test in this file makes a
    real network call or has its exact usage/cost assertions shifted."""
    monkeypatch.setattr(
        service.llm_service,
        "embed_texts",
        lambda texts, **kwargs: EmbeddingResult(
            vectors=[[0.0] * EMBEDDING_WIDTH for _ in texts],
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0, cost_usd=None),
        ),
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
    "item_moved": {
        "movement": "taken",
        "actor_id": "obj-1",
        "actor_name": "Hero",
        "item_id": "obj-2",
        "item_name": "Rusty Sword",
    },
    "hp_changed": {
        "target_id": "obj-2",
        "target_name": "Goblin",
        "before": 7,
        "after": 3,
        "max_hp": 7,
        "alive": True,
        "down": False,
    },
    "way_opened": {
        "actor_id": "obj-1",
        "actor_name": "Hero",
        "object_id": "obj-3",
        "object_name": "Iron Door",
        "action": "pick_lock",
    },
    "rule_looked_up": {"topic": "Chapter 7 › Using Ability Scores › Hiding"},
}


@pytest.mark.parametrize("event_type", sorted(VALID_PAYLOADS))
def test_accepts_and_stores_each_of_the_sixteen_types(event_type):
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


@pytest.mark.parametrize(
    "event_type,bad_payload",
    [
        ("item_moved", {**VALID_PAYLOADS["item_moved"], "movement": "traded"}),
        ("item_moved", {k: v for k, v in VALID_PAYLOADS["item_moved"].items() if k != "item_id"}),
        ("hp_changed", {k: v for k, v in VALID_PAYLOADS["hp_changed"].items() if k != "after"}),
        ("way_opened", {**VALID_PAYLOADS["way_opened"], "extra_field": True}),
        ("rule_looked_up", {}),
    ],
)
def test_new_kind_malformed_payload_is_refused_and_writes_nothing(event_type, bad_payload):
    db = FakeSession()

    with pytest.raises(InvalidEventPayloadError):
        asyncio.run(
            service.append_event(
                db, run_id="run-1", type=event_type, visibility="player", payload=bad_payload
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
    # A non-narration type: narration's own embedding usage is exercised in
    # `test_append_event_narration_embedding.py` (AC2) and does populate
    # `prompt_tokens`/`cost_usd` even with no caller `usage`.
    db = FakeSession()

    event = asyncio.run(
        service.append_event(
            db, run_id="run-1", type="player_action", visibility="player", payload={"text": "hi"}
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
        (ItemMovedPayload, VALID_PAYLOADS["item_moved"]),
        (HpChangedPayload, VALID_PAYLOADS["hp_changed"]),
        (WayOpenedPayload, VALID_PAYLOADS["way_opened"]),
        (RuleLookedUpPayload, VALID_PAYLOADS["rule_looked_up"]),
    ],
)
def test_payload_models_round_trip_their_own_valid_dict(model_cls, payload):
    assert model_cls.model_validate(payload).model_dump(by_alias=True)


def test_scene_entered_payload_scene_title_is_optional_for_older_rows():
    # `scene_title` (sprint 010/04) is absent on rows written before this
    # field existed -- omitting it must still validate, not just defaulting
    # to `None` when explicitly passed.
    payload = SceneEnteredPayload.model_validate(VALID_PAYLOADS["scene_entered"])
    assert payload.scene_title is None
    assert "sceneTitle" not in payload.model_dump(by_alias=True, exclude_none=True)


def test_item_moved_to_id_and_to_name_are_none_unless_given():
    payload = ItemMovedPayload.model_validate(VALID_PAYLOADS["item_moved"])
    assert payload.to_id is None
    assert payload.to_name is None
