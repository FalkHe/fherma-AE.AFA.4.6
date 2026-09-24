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
    def __init__(self, snapshot: _Snapshot):
        self._snapshot = snapshot
        self.ainvoke_calls: list[Any] = []

    async def aget_state(self, config):
        return self._snapshot

    async def ainvoke(self, payload, config=None, **kwargs):
        self.ainvoke_calls.append(payload)
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


def _install_agent(monkeypatch, snapshot: _Snapshot) -> _FakeAgent:
    agent = _FakeAgent(snapshot)
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
