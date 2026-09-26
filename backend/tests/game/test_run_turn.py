"""`game.service.run_turn` (sprint 011/08, WI2, I2): which of five kinds a
turn is, read from the DM thread's own checkpoint alone, and what each
kind hands the compiled graph. The graph itself is monkeypatched wholesale
-- `build_agent` returns a `_FakeAgent` whose `aget_state`/`ainvoke` this
suite scripts directly -- so this file proves the *wiring*, never the
graph's own behaviour (that is `agent/flow_nodes.py`'s and the sprint's
`test_scenarios_database.py`'s job).

One exception (sprint 011/08 round 2, defect ← finding): a real
compiled graph, real `InMemorySaver` and `ScriptedChatModel`, driven
through `run_turn` itself twice -- the action that pauses for a roll,
then the roll press exactly as the frontend sends it (`text=None`) --
since the wiring-only fakes above cannot catch a resume payload
langgraph itself refuses to treat as a value (an empty `dict`, read as a
resume-by-interrupt-id map instead).
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from sqlalchemy import text as sql_text

from app.core.checkpointer import service as checkpointer_service
from app.core.ids import generate_id
from app.modules.game import service as game_service
from app.modules.game.agent import flow_nodes
from app.modules.game.agent.decisions import MoveAssessmentOut, ReadMoveOut
from app.modules.game.agent.flow_state import AwaitingRef, TurnFrame
from app.modules.game.errors import ActionNotAvailableError
from app.modules.playthrough import service as playthrough_service
from tests.game.fakes import ScriptedChatModel

# `_stub_common` (autouse below) monkeypatches `flow_nodes.set_runtime` to
# a no-op for every test in this file; the one real-graph test restores it
# from this reference, captured before any test can shadow it.
_REAL_SET_RUNTIME = flow_nodes.set_runtime

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


def test_a_fresh_action_turn_carries_a_running_fight_forward(monkeypatch):
    """← finding (run 01M3E8VSFCZ856D2SNFATQXAPM): a fight spans several
    player turns, but every fresh action turn used to invoke the graph
    with `initial_state`'s own `combat=None`, wiping whatever fight was
    already under way and forcing initiative to be rolled again. The
    previous checkpoint's own `combat` must survive onto the new turn's
    starting state."""

    async def _run():
        _stub_get_awaiting(monkeypatch, "none")
        combat = {"scene_id": "scene-1", "order": ["hero-1", "goblin-1"], "index": 1, "round": 1}
        agent = _install_agent(
            monkeypatch, _Snapshot(values={"turn": _turn_frame(), "combat": combat})
        )

        async def fake_record_player_action(db, **kwargs):
            return None

        monkeypatch.setattr(playthrough_service, "record_player_action", fake_record_player_action)

        outcome = await game_service.run_turn(
            object(), user_id=USER_ID, run_id=RUN_ID, text="I attack the goblin again"
        )

        assert outcome.kind == "action"
        [state] = agent.ainvoke_calls
        assert state["combat"] == combat

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
        assert resume.resume == {"acknowledged": True}

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


def test_a_roll_left_by_a_pre_migration_checkpoint_is_resolved_without_invoking_the_graph(
    monkeypatch,
):
    """← migration case: `aget_state` on a checkpoint written before this
    flow existed (no `turn`/`awaiting` channel it ever declared) comes
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


def test_a_question_left_by_a_pre_migration_checkpoint_is_answered_then_continues_as_a_fresh_action(
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


def test_an_off_menu_answer_to_a_question_left_by_a_pre_migration_checkpoint_is_refused(
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


def test_a_new_flow_awaiting_takes_precedence_over_any_pre_migration_check(monkeypatch):
    """A checkpoint that already carries `turn` is never treated as a
    pre-migration checkpoint, even when `get_awaiting` would report an
    open request -- the normal `awaiting` branch alone decides."""

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
        assert resume.resume == {"acknowledged": True}
        # `get_awaiting` is consulted once, only to populate the returned
        # outcome -- never to decide the turn's kind, since `turn` was
        # already present in the checkpoint.
        assert get_awaiting_calls == [RUN_ID]

    asyncio.run(_run())


_CAMPAIGN_ID = "greenhollow"
_TO_THORNWAY = "to-thornway"


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        sql_text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _setup_run(db, *, username: str) -> tuple[str, str, str]:
    """Same path `test_scenarios_database.py`'s own `_setup_run` walks --
    duplicated rather than imported, since that module's helpers are
    private to its own suite."""
    owner_id = generate_id()
    await _insert_user(db, owner_id, username=username)
    await db.commit()
    run = await playthrough_service.start_campaign_run(
        db, user_id=owner_id, campaign_id=_CAMPAIGN_ID
    )
    character = await playthrough_service.create_character(db, user_id=owner_id, run_id=run.id)
    await playthrough_service.enter_adventure(db, user_id=owner_id, run_id=run.id)
    return owner_id, run.id, character.id


@pytest.mark.database
def test_run_turn_resumes_a_paused_roll_and_writes_it(playthrough_db, monkeypatch):
    """← sprint 011/08 round 2, defect: `Command(resume={})` -- an empty
    dict -- is read by langgraph 1.2.11 as a resume-by-interrupt-id map,
    not a value for the one pending interrupt, so it never actually
    resumed: the turn returned 200, wrote no event, and the thread stayed
    at `next=('await_player',)`. Drives a real pause-for-a-roll turn
    through `run_turn` itself twice, over a real compiled graph and a real
    `InMemorySaver`: the action that triggers the check, then the roll
    press exactly as the frontend sends it (`text=None`,
    `useTakeTurn.roll`)."""

    async def _run():
        db = playthrough_db
        owner_id, run_id, hero_id = await _setup_run(db, username="run-turn-roll-flow")
        await playthrough_service.use_exit(
            db, user_id=owner_id, actor_id=hero_id, exit_id=_TO_THORNWAY
        )

        saver = InMemorySaver(serde=checkpointer_service.checkpoint_serde())

        @asynccontextmanager
        async def fake_checkpointer():
            yield saver

        monkeypatch.setattr(checkpointer_service, "checkpointer", fake_checkpointer)
        monkeypatch.setattr(flow_nodes, "set_runtime", _REAL_SET_RUNTIME)

        model = ScriptedChatModel(
            [
                AIMessage(content="Rosalind crouches over the low thorn."),
                ReadMoveOut(intent="search", refs={}, proposed=None),
                MoveAssessmentOut(
                    applies=True,
                    dc=5,
                    dc_source="authored",
                    consequence_ids=[],
                    secret_index=0,
                    fixture_id=None,
                    check_action=None,
                ),
                "The widened cut confirms something heavy has passed this way more than once.",
            ]
        )
        monkeypatch.setattr(game_service, "chat_model", lambda: model)

        search_text = "I search the wool-marked narrow cut at ankle height for signs of passage."
        outcome = await game_service.run_turn(db, user_id=owner_id, run_id=run_id, text=search_text)
        assert outcome.kind == "action"
        assert outcome.awaiting.startswith("roll:")

        # The roll button itself: `text: null`.
        outcome2 = await game_service.run_turn(db, user_id=owner_id, run_id=run_id, text=None)
        assert outcome2.kind == "roll"
        assert outcome2.awaiting == "none"

        rows = (
            await db.execute(
                sql_text(
                    "SELECT id, type, payload FROM events WHERE campaign_run_id = :run_id "
                    "ORDER BY id"
                ),
                {"run_id": run_id},
            )
        ).all()
        roll_requested = [row for row in rows if row.type == "roll_requested"]
        rolls = [row for row in rows if row.type == "roll"]
        assert len(roll_requested) == 1
        assert len(rolls) == 1
        assert rolls[0].payload["requestId"] == roll_requested[0].id

    asyncio.run(_run())
