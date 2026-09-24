"""`game.service.run_turn` (sprint 011/08, WI2, I2): which of five kinds a
turn is, read from the DM thread's own checkpoint alone, and what each
kind hands the compiled graph. The graph itself is monkeypatched wholesale
-- `build_agent` returns a `_FakeAgent` whose `aget_state`/`ainvoke` this
suite scripts directly -- so this file proves the *wiring*, never the
graph's own behaviour (that is `agent/flow_nodes.py`'s and the sprint's
`test_scenarios_database.py`'s job).
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from langgraph.types import Command

from app.modules.game import service as game_service
from app.modules.game.agent import flow_nodes
from app.modules.game.agent.flow_state import AwaitingRef, TurnFrame
from app.modules.game.errors import ActionNotAvailableError
from app.modules.playthrough import service as playthrough_service

USER_ID = "user-1"
RUN_ID = "run-1"
HERO_ID = "hero-1"


@dataclass
class _Character:
    id: str = HERO_ID


@dataclass
class _Snapshot:
    values: dict[str, Any]
    next: tuple[str, ...] = ()


class _FakeAgent:
    def __init__(
        self,
        snapshot: _Snapshot | None = None,
        *,
        snapshots: dict[str, _Snapshot] | None = None,
    ):
        self._snapshot = snapshot
        self._snapshots = snapshots or {}
        self.ainvoke_calls: list[Any] = []
        self.ainvoke_thread_ids: list[str] = []

    async def aget_state(self, config):
        thread_id = config["configurable"]["thread_id"]
        if thread_id in self._snapshots:
            return self._snapshots[thread_id]
        if self._snapshot is not None:
            return self._snapshot
        return _Snapshot(values={})

    async def ainvoke(self, payload, config=None, **kwargs):
        self.ainvoke_calls.append(payload)
        self.ainvoke_thread_ids.append(config["configurable"]["thread_id"] if config else None)
        return {}


def _turn_frame(**overrides) -> TurnFrame:
    base = dict(
        run_id=RUN_ID,
        hero_id=HERO_ID,
        turn_id="open-turn-1",
        input_kind="action",
        text="I look around",
        status="open",
        round_admitted=False,
    )
    return TurnFrame(**{**base, **overrides})


@pytest.fixture(autouse=True)
def _stub_common(monkeypatch):
    async def fake_get_member_character(db, *, user_id, run_id):
        return _Character()

    monkeypatch.setattr(playthrough_service, "get_member_character", fake_get_member_character)
    monkeypatch.setattr(game_service, "chat_model", lambda: object())

    @asynccontextmanager
    async def fake_checkpointer():
        yield object()

    from app.core.checkpointer import service as checkpointer_service

    monkeypatch.setattr(checkpointer_service, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(flow_nodes, "set_runtime", lambda runtime: None)


def _install_agent(
    monkeypatch, snapshot: _Snapshot | None = None, *, snapshots: dict[str, _Snapshot] | None = None
) -> _FakeAgent:
    agent = _FakeAgent(snapshot, snapshots=snapshots)
    monkeypatch.setattr(game_service, "build_agent", lambda **kwargs: agent)
    return agent


def _stub_get_awaiting(monkeypatch, value: str):
    async def fake_get_awaiting(db, *, user_id, run_id):
        return value

    monkeypatch.setattr(playthrough_service, "get_awaiting", fake_get_awaiting)


def test_opening_turn_invokes_initial_state_with_no_text(monkeypatch):
    async def _run():
        _stub_get_awaiting(monkeypatch, "none")
        agent = _install_agent(monkeypatch, _Snapshot(values={}))

        outcome = await game_service.run_turn(object(), user_id=USER_ID, run_id=RUN_ID, text=None)

        assert outcome.kind == "opening"
        assert outcome.awaiting == "none"
        [state] = agent.ainvoke_calls
        assert state["turn"].input_kind == "opening"
        assert state["turn"].text is None
        assert state["turn"].hero_id == HERO_ID

    asyncio.run(_run())


def test_action_turn_records_player_action_then_invokes_initial_state(monkeypatch):
    async def _run():
        _stub_get_awaiting(monkeypatch, "none")
        agent = _install_agent(monkeypatch, _Snapshot(values={}))

        recorded = []

        async def fake_record_player_action(db, *, user_id, run_id, text, turn_id):
            recorded.append(
                {"user_id": user_id, "run_id": run_id, "text": text, "turn_id": turn_id}
            )

        monkeypatch.setattr(playthrough_service, "record_player_action", fake_record_player_action)

        outcome = await game_service.run_turn(
            object(), user_id=USER_ID, run_id=RUN_ID, text="I open the door"
        )

        assert outcome.kind == "action"
        assert len(recorded) == 1
        assert recorded[0]["text"] == "I open the door"
        assert recorded[0]["turn_id"] == outcome.turn_id
        [state] = agent.ainvoke_calls
        assert state["turn"].input_kind == "action"
        assert state["turn"].text == "I open the door"
        assert state["turn"].turn_id == outcome.turn_id

    asyncio.run(_run())


def test_roll_answer_resumes_with_an_empty_payload_and_writes_no_row_itself(monkeypatch):
    async def _run():
        _stub_get_awaiting(monkeypatch, "none")
        awaiting = AwaitingRef(
            request_id="req-1",
            kind="roll",
            actor_id=HERO_ID,
            public={"ability": "dexterity", "skill": None, "dc": 12},
            consumer="resolve_check",  # type: ignore[arg-type]
            consumer_payload={},
        )
        agent = _install_agent(
            monkeypatch, _Snapshot(values={"turn": _turn_frame(), "awaiting": awaiting})
        )

        async def fail_record_player_action(db, **kwargs):
            raise AssertionError("run_turn must not write a player row for a roll resume")

        monkeypatch.setattr(playthrough_service, "record_player_action", fail_record_player_action)

        outcome = await game_service.run_turn(
            object(), user_id=USER_ID, run_id=RUN_ID, text="97 ignored"
        )

        assert outcome.kind == "roll"
        assert outcome.turn_id == "open-turn-1"
        [resume] = agent.ainvoke_calls
        assert isinstance(resume, Command)
        assert resume.resume == {}

    asyncio.run(_run())


def test_choice_answer_resumes_with_the_offered_text_and_writes_no_row_itself(monkeypatch):
    async def _run():
        _stub_get_awaiting(monkeypatch, "none")
        awaiting = AwaitingRef(
            request_id="req-2",
            kind="choice",
            actor_id=HERO_ID,
            public={"text": "Sneak or run?", "options": ["Sneak", "Run"]},
            consumer="accept_choice",  # type: ignore[arg-type]
            consumer_payload={},
        )
        agent = _install_agent(
            monkeypatch, _Snapshot(values={"turn": _turn_frame(), "awaiting": awaiting})
        )

        async def fail_record_player_action(db, **kwargs):
            raise AssertionError("run_turn must not write a player row for a choice resume")

        monkeypatch.setattr(playthrough_service, "record_player_action", fail_record_player_action)

        outcome = await game_service.run_turn(
            object(), user_id=USER_ID, run_id=RUN_ID, text="Sneak"
        )

        assert outcome.kind == "answer"
        assert outcome.turn_id == "open-turn-1"
        [resume] = agent.ainvoke_calls
        assert isinstance(resume, Command)
        assert resume.resume == "Sneak"

    asyncio.run(_run())


def test_a_stale_or_off_menu_answer_is_refused_without_a_resume(monkeypatch):
    async def _run():
        _stub_get_awaiting(monkeypatch, "answer:req-2")
        awaiting = AwaitingRef(
            request_id="req-2",
            kind="choice",
            actor_id=HERO_ID,
            public={"text": "Sneak or run?", "options": ["Sneak", "Run"]},
            consumer="accept_choice",  # type: ignore[arg-type]
            consumer_payload={},
        )
        agent = _install_agent(
            monkeypatch, _Snapshot(values={"turn": _turn_frame(), "awaiting": awaiting})
        )

        with pytest.raises(ActionNotAvailableError) as exc_info:
            await game_service.run_turn(
                object(), user_id=USER_ID, run_id=RUN_ID, text="I set fire to the village"
            )

        assert exc_info.value.details == {
            "awaiting": "answer:req-2",
            "options": ["Sneak", "Run"],
        }
        assert agent.ainvoke_calls == []

    asyncio.run(_run())


def test_retry_resumes_with_none_from_the_last_saved_step(monkeypatch):
    async def _run():
        _stub_get_awaiting(monkeypatch, "none")
        agent = _install_agent(
            monkeypatch,
            _Snapshot(values={"turn": _turn_frame()}, next=("advance",)),
        )

        outcome = await game_service.run_turn(object(), user_id=USER_ID, run_id=RUN_ID, text=None)

        assert outcome.kind == "retry"
        assert outcome.turn_id == "open-turn-1"
        assert agent.ainvoke_calls == [None]

    asyncio.run(_run())


def test_a_roll_left_by_the_old_flow_is_resolved_without_invoking_the_graph(monkeypatch):
    """← sprint 011/08 round 1, defect B: `aget_state` on a checkpoint the
    old flow wrote (no `turn`/`awaiting` channel it ever declared) comes
    back with empty `values` -- identical to a thread never touched -- but
    a transcript still waiting on a `roll_requested` must not fall into
    the stale-request refusal."""

    async def _run():
        agent = _install_agent(monkeypatch, _Snapshot(values={}))

        awaiting_calls = ["roll:req-old-1", "none"]

        async def fake_get_awaiting(db, *, user_id, run_id):
            return awaiting_calls.pop(0)

        monkeypatch.setattr(playthrough_service, "get_awaiting", fake_get_awaiting)

        async def fake_open_turn_id(db, **k):
            return "legacy-turn-1"

        monkeypatch.setattr(playthrough_service, "open_turn_id", fake_open_turn_id)

        resolved = []

        async def fake_resolve_roll_request(db, *, user_id, request_id, turn_id=None):
            resolved.append({"request_id": request_id, "turn_id": turn_id})

        monkeypatch.setattr(playthrough_service, "resolve_roll_request", fake_resolve_roll_request)

        # The roll button itself always sends `text: null` -- the server
        # rolls, never a caller-sent number (`useTakeTurn.roll`).
        outcome = await game_service.run_turn(object(), user_id=USER_ID, run_id=RUN_ID, text=None)

        assert outcome.kind == "roll"
        assert outcome.awaiting == "none"
        assert resolved == [{"request_id": "req-old-1", "turn_id": "legacy-turn-1"}]
        assert agent.ainvoke_calls == []

    asyncio.run(_run())


def test_a_question_left_by_the_old_flow_is_answered_then_continues_as_a_fresh_action(
    monkeypatch,
):
    async def _run():
        agent = _install_agent(monkeypatch, _Snapshot(values={}))

        async def fake_get_awaiting(db, *, user_id, run_id):
            return "answer:question-old-1"

        monkeypatch.setattr(playthrough_service, "get_awaiting", fake_get_awaiting)

        @dataclass
        class _QuestionEvent:
            id: str
            payload: dict

        async def fake_list_events(db, *, user_id, run_id, after=None, limit=200):
            return [_QuestionEvent(id="question-old-1", payload={"options": ["Sneak", "Run"]})]

        monkeypatch.setattr(playthrough_service, "list_events", fake_list_events)

        recorded_answers = []

        async def fake_record_answer(db, *, user_id, run_id, text, question_id, turn_id):
            recorded_answers.append({"text": text, "question_id": question_id, "turn_id": turn_id})

        monkeypatch.setattr(playthrough_service, "record_answer", fake_record_answer)

        outcome = await game_service.run_turn(
            object(), user_id=USER_ID, run_id=RUN_ID, text="Sneak"
        )

        assert outcome.kind == "action"
        assert len(recorded_answers) == 1
        assert recorded_answers[0]["text"] == "Sneak"
        assert recorded_answers[0]["question_id"] == "question-old-1"
        [state] = agent.ainvoke_calls
        assert state["turn"].input_kind == "action"
        assert state["turn"].text == "Sneak"
        assert agent.ainvoke_thread_ids == [RUN_ID]

    asyncio.run(_run())


def test_an_off_menu_answer_to_a_question_left_by_the_old_flow_is_refused(monkeypatch):
    async def _run():
        agent = _install_agent(monkeypatch, _Snapshot(values={}))

        async def fake_get_awaiting(db, *, user_id, run_id):
            return "answer:question-old-1"

        monkeypatch.setattr(playthrough_service, "get_awaiting", fake_get_awaiting)

        @dataclass
        class _QuestionEvent:
            id: str
            payload: dict

        async def fake_list_events(db, *, user_id, run_id, after=None, limit=200):
            return [_QuestionEvent(id="question-old-1", payload={"options": ["Sneak", "Run"]})]

        monkeypatch.setattr(playthrough_service, "list_events", fake_list_events)

        with pytest.raises(ActionNotAvailableError) as exc_info:
            await game_service.run_turn(
                object(), user_id=USER_ID, run_id=RUN_ID, text="Set fire to the village"
            )

        assert exc_info.value.details == {
            "awaiting": "answer:question-old-1",
            "options": ["Sneak", "Run"],
        }
        assert agent.ainvoke_calls == []

    asyncio.run(_run())


def test_a_new_flow_awaiting_takes_precedence_over_any_legacy_check(monkeypatch):
    """A checkpoint that already carries `turn` is never treated as legacy,
    even when `get_awaiting` would report an open request -- the normal
    `awaiting` branch alone decides."""

    async def _run():
        awaiting = AwaitingRef(
            request_id="req-3",
            kind="roll",
            actor_id=HERO_ID,
            public={"ability": "dexterity", "skill": None, "dc": 12},
            consumer="resolve_check",  # type: ignore[arg-type]
            consumer_payload={},
        )
        agent = _install_agent(
            monkeypatch, _Snapshot(values={"turn": _turn_frame(), "awaiting": awaiting})
        )

        get_awaiting_calls = []

        async def fake_get_awaiting(db, *, user_id, run_id):
            get_awaiting_calls.append(run_id)
            return "none"

        monkeypatch.setattr(playthrough_service, "get_awaiting", fake_get_awaiting)

        outcome = await game_service.run_turn(
            object(), user_id=USER_ID, run_id=RUN_ID, text="97 ignored"
        )

        assert outcome.kind == "roll"
        [resume] = agent.ainvoke_calls
        assert isinstance(resume, Command)
        assert resume.resume == {}
        # `get_awaiting` is consulted once, only to populate the returned
        # outcome -- never to decide the turn's kind, since `turn` was
        # already present in the checkpoint.
        assert get_awaiting_calls == [RUN_ID]

    asyncio.run(_run())
