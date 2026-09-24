"""Sprint 010/03, WI1: `game.service.run_turn` -- the turn engine that
decides which of five kinds a turn is from the DM thread's own checkpoint
state and the transcript, never from what the caller claims.

`run_turn`'s own building blocks (`turn`, `resume`, `retry`, `thread_state`,
`build_agent`, the checkpointer) are stubbed out for most of this file:
those tests prove the *dispatch* logic alone -- which kind is picked,
which id is reused or minted, and what gets written before a resume.
`test_a_broken_turn_retry_resumes_the_real_graph_without_repeating_the_roll`
below is the one exception: it drives the real graph the way
`test_service.py`/`test_narrate_seam.py` do, so AC4 (a broken turn's
retry) has more than a stubbed assertion that the right branch was taken.

Prefixed `test_run_turn_engine` (not `test_service_turn` or similar) so it
never collides with WI3's acceptance suite over the HTTP route.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.checkpointer import service as checkpointer_service
from app.core.errors import ErrorCode
from app.core.llm.errors import LlmAuthError
from app.modules.game import service
from app.modules.game.agent import nodes, tools
from app.modules.game.agent.state import DmContext
from app.modules.game.errors import ActionNotAvailableError
from app.modules.playthrough.errors import CampaignRunNotFoundError


@dataclass
class _Character:
    id: str = "actor-1"


class _Db:
    """Stands in for the caller's `AsyncSession`: `run_turn` never reads
    from it directly, only passes it through and, on the `answer` leg,
    commits it once before resuming."""

    def __init__(self, order: list[str]) -> None:
        self._order = order

    async def commit(self) -> None:
        self._order.append("commit")


@pytest.fixture
def engine(monkeypatch):
    """Stubs every building block `run_turn` composes, each recording its
    call onto `calls`, and lets a test steer the DM thread's own state
    (`thread.value`), the open turn id (`open_turn.value`) and the
    post-turn `awaiting` read (`awaiting.value`) before calling `run_turn`.
    """
    calls = SimpleNamespace(
        resume=[],
        retry=[],
        turn=[],
        open_turn_id=[],
        get_awaiting=[],
        append_event=[],
        checkpointer_opened=False,
        order=[],
    )
    thread = SimpleNamespace(value=None)
    open_turn = SimpleNamespace(value=None)
    awaiting = SimpleNamespace(value="none")

    @asynccontextmanager
    async def fake_checkpointer():
        calls.checkpointer_opened = True
        yield "saver-sentinel"

    monkeypatch.setattr(service.checkpointer_service, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(service, "build_agent", lambda **kwargs: "agent-sentinel")

    async def fake_thread_state(agent, *, thread_id):
        return thread.value

    monkeypatch.setattr(service, "thread_state", fake_thread_state)

    async def fake_get_member_character(db, *, user_id, run_id):
        return _Character()

    monkeypatch.setattr(
        service.playthrough_service, "get_member_character", fake_get_member_character
    )

    async def fake_open_turn_id(db, *, user_id, run_id):
        calls.open_turn_id.append({"user_id": user_id, "run_id": run_id})
        return open_turn.value

    monkeypatch.setattr(service.playthrough_service, "open_turn_id", fake_open_turn_id)

    async def fake_get_awaiting(db, *, user_id, run_id):
        calls.get_awaiting.append({"user_id": user_id, "run_id": run_id})
        return awaiting.value

    monkeypatch.setattr(service.playthrough_service, "get_awaiting", fake_get_awaiting)

    async def fake_append_event(db, **kwargs):
        calls.append_event.append(kwargs)
        calls.order.append("append_event")

    monkeypatch.setattr(service.playthrough_service, "append_event", fake_append_event)

    async def fake_resume(agent, *, thread_id, context, resume_value):
        calls.resume.append(
            {
                "agent": agent,
                "thread_id": thread_id,
                "context": context,
                "resume_value": resume_value,
            }
        )
        calls.order.append("resume")

    monkeypatch.setattr(service, "resume", fake_resume)

    async def fake_retry(agent, *, thread_id, context):
        calls.retry.append({"agent": agent, "thread_id": thread_id, "context": context})
        calls.order.append("retry")

    monkeypatch.setattr(service, "retry", fake_retry)

    async def fake_turn(agent, *, thread_id, context, player_text):
        calls.turn.append(
            {"agent": agent, "thread_id": thread_id, "context": context, "player_text": player_text}
        )
        calls.order.append("turn")

    monkeypatch.setattr(service, "turn", fake_turn)

    return SimpleNamespace(calls=calls, thread=thread, open_turn=open_turn, awaiting=awaiting)


def _run(db, **kwargs):
    return asyncio.run(service.run_turn(db, **kwargs))


def test_a_pending_question_is_answered_then_stops_being_awaited(engine):
    engine.thread.value = service.ThreadState(
        interrupt={"type": "question", "question_id": "q-1", "text": "Pick", "options": ["A", "B"]},
        pending=False,
    )
    engine.open_turn.value = "turn-open-1"
    engine.awaiting.value = "none"
    order: list[str] = []
    db = _Db(order)
    engine.calls.order = order

    outcome = _run(db, user_id="u1", run_id="r1", text="A")

    assert outcome == service.TurnOutcome(turn_id="turn-open-1", kind="answer", awaiting="none")
    assert engine.calls.append_event == [
        {
            "run_id": "r1",
            "type": "player_action",
            "visibility": "player",
            "payload": {"text": "A", "answersQuestionId": "q-1"},
            "turn_id": "turn-open-1",
        }
    ]
    assert engine.calls.order == ["append_event", "commit", "resume"]
    assert len(engine.calls.resume) == 1
    resumed = engine.calls.resume[0]
    assert resumed["thread_id"] == "r1"
    assert resumed["resume_value"] == "A"
    assert resumed["context"] == DmContext(
        db=db, user_id="u1", actor_id="actor-1", run_id="r1", turn_id="turn-open-1"
    )


def test_an_answer_not_among_the_options_is_refused_unwritten_and_unresumed(engine):
    engine.thread.value = service.ThreadState(
        interrupt={"type": "question", "question_id": "q-1", "text": "Pick", "options": ["A", "B"]},
        pending=False,
    )
    engine.awaiting.value = "answer:q-1"

    with pytest.raises(ActionNotAvailableError) as exc_info:
        _run(object(), user_id="u1", run_id="r1", text="C")

    assert exc_info.value.code == ErrorCode.ACTION_NOT_AVAILABLE
    assert exc_info.value.details == {"awaiting": "answer:q-1", "options": ["A", "B"]}
    assert engine.calls.append_event == []
    assert engine.calls.resume == []


def test_a_question_with_no_options_accepts_any_answer(engine):
    engine.thread.value = service.ThreadState(
        interrupt={"type": "question", "question_id": "q-2", "text": "Go on.", "options": []},
        pending=False,
    )
    engine.open_turn.value = "turn-open-2"

    outcome = _run(_Db([]), user_id="u1", run_id="r1", text="whatever I like")

    assert outcome.kind == "answer"
    assert engine.calls.append_event[0]["payload"] == {
        "text": "whatever I like",
        "answersQuestionId": "q-2",
    }
    assert len(engine.calls.resume) == 1


def test_a_pending_roll_request_always_rolls_and_ignores_the_bodys_number(engine):
    engine.thread.value = service.ThreadState(
        interrupt={
            "type": "roll_request",
            "request_id": "req-1",
            "kind": "ability_check",
            "formula": "1d20+2",
            "actor_id": "actor-1",
            "context": {},
        },
        pending=False,
    )
    engine.open_turn.value = "turn-open-3"

    outcome = _run(object(), user_id="u1", run_id="r1", text="42")

    assert outcome.kind == "roll"
    assert outcome.turn_id == "turn-open-3"
    # No player row for a roll leg -- the roll itself is what gets recorded,
    # by the tool that already requested it.
    assert engine.calls.append_event == []
    assert engine.calls.resume == [
        {
            "agent": "agent-sentinel",
            "thread_id": "r1",
            "context": DmContext(
                db=engine.calls.resume[0]["context"].db,
                user_id="u1",
                actor_id="actor-1",
                run_id="r1",
                turn_id="turn-open-3",
            ),
            "resume_value": {"action": "roll"},
        }
    ]


def test_a_broken_turn_retries_from_the_saved_step_without_replaying_the_turn(engine):
    engine.thread.value = service.ThreadState(interrupt=None, pending=True)
    engine.open_turn.value = "turn-open-4"

    outcome = _run(object(), user_id="u1", run_id="r1", text="anything, ignored")

    assert outcome.kind == "retry"
    assert outcome.turn_id == "turn-open-4"
    assert len(engine.calls.retry) == 1
    assert engine.calls.resume == []
    assert engine.calls.turn == []
    assert engine.calls.append_event == []


def test_a_broken_turn_with_nothing_recorded_yet_still_gets_a_real_turn_id(engine):
    """Regression: a leg that broke before writing any event at all (an
    opening turn that crashed in `narrate` before its first narration) has
    no open turn for `open_turn_id` to reuse -- it answers `None`. `retry`
    must still continue under a real, freshly minted id, never `None`
    (which would fail `TurnOutcome.turn_id: str`, and the route's
    `TurnRead.turn_id: str` behind it)."""
    engine.thread.value = service.ThreadState(interrupt=None, pending=True)
    engine.open_turn.value = None

    outcome = _run(object(), user_id="u1", run_id="r1", text="")

    assert outcome.kind == "retry"
    assert isinstance(outcome.turn_id, str)
    assert outcome.turn_id != ""
    assert len(engine.calls.retry) == 1
    assert engine.calls.retry[0]["context"].turn_id == outcome.turn_id
    assert engine.calls.turn == []


def test_a_fresh_action_mints_a_new_turn_id_never_reusing_the_open_one(engine):
    engine.thread.value = service.ThreadState(interrupt=None, pending=False)
    engine.open_turn.value = "turn-open-should-never-be-read"

    outcome = _run(object(), user_id="u1", run_id="r1", text="I open the door.")

    assert outcome.kind == "action"
    assert outcome.turn_id != "turn-open-should-never-be-read"
    assert engine.calls.open_turn_id == []
    assert len(engine.calls.turn) == 1
    called = engine.calls.turn[0]
    assert called["player_text"] == "I open the door."
    assert called["context"].turn_id == outcome.turn_id
    assert called["context"].record_action is True


def test_no_text_is_an_opening_turn_that_suppresses_the_player_row(engine):
    engine.thread.value = service.ThreadState(interrupt=None, pending=False)

    outcome = _run(object(), user_id="u1", run_id="r1", text="")

    assert outcome.kind == "opening"
    assert engine.calls.open_turn_id == []
    assert len(engine.calls.turn) == 1
    called = engine.calls.turn[0]
    assert called["player_text"] == ""
    assert called["context"].record_action is False
    assert engine.calls.append_event == []


def test_no_text_field_at_all_is_also_an_opening_turn(engine):
    """The wire request's `text` is optional (`TurnRequest.text: str |
    None`) -- `None`, not only `""`, must take the opening branch."""
    engine.thread.value = service.ThreadState(interrupt=None, pending=False)

    outcome = _run(object(), user_id="u1", run_id="r1", text=None)

    assert outcome.kind == "opening"
    assert engine.calls.turn[0]["context"].record_action is False


def test_no_text_with_a_stale_awaiting_request_refuses_instead_of_writing_filler(engine):
    """Sprint 010/11 round 4, Fault A -- ← finding: no real interrupt is
    pending and nothing is queued to retry, yet `get_awaiting` still names
    something (a stale or dangling request `get_awaiting`'s own actor
    check did not exclude). Posting `{text: null}` here used to fall
    through to a DM-led opening turn that narrated filler instead of
    resolving anything -- it must refuse, unwritten, the same shape a bad
    answer already refuses."""
    engine.thread.value = service.ThreadState(interrupt=None, pending=False)
    engine.awaiting.value = "roll:stale-req-1"

    with pytest.raises(ActionNotAvailableError) as exc_info:
        _run(object(), user_id="u1", run_id="r1", text=None)

    assert exc_info.value.code == ErrorCode.ACTION_NOT_AVAILABLE
    assert exc_info.value.details == {"awaiting": "roll:stale-req-1", "options": []}
    assert engine.calls.turn == []
    assert engine.calls.append_event == []


def test_a_caller_not_seated_at_the_run_is_refused_before_touching_the_thread(engine, monkeypatch):
    async def refuse(db, *, user_id, run_id):
        raise CampaignRunNotFoundError(run_id)

    monkeypatch.setattr(service.playthrough_service, "get_member_character", refuse)

    with pytest.raises(CampaignRunNotFoundError):
        _run(object(), user_id="u1", run_id="r1", text="hello")

    assert engine.calls.checkpointer_opened is False


def test_record_action_writes_a_player_row_by_default(monkeypatch):
    calls: list[dict] = []
    order: list[str] = []

    async def fake_append_event(db, **kwargs):
        calls.append(kwargs)
        order.append("append_event")

    monkeypatch.setattr(nodes.playthrough_service, "append_event", fake_append_event)

    ctx = DmContext(db=_Db(order), user_id="u1", run_id="r1", turn_id="t1")
    runtime = SimpleNamespace(context=ctx)
    node = nodes.make_record_action()

    asyncio.run(node({"messages": [HumanMessage(content="I look around.")]}, runtime=runtime))

    assert calls == [
        {
            "run_id": "r1",
            "type": "player_action",
            "visibility": "player",
            "payload": {"text": "I look around."},
            "turn_id": "t1",
        }
    ]
    assert order == ["append_event", "commit"]


def test_record_action_is_suppressed_for_an_opening_turn(monkeypatch):
    calls: list[dict] = []

    async def fake_append_event(db, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(nodes.playthrough_service, "append_event", fake_append_event)

    ctx = DmContext(db=object(), user_id="u1", run_id="r1", turn_id="t1", record_action=False)
    runtime = SimpleNamespace(context=ctx)
    node = nodes.make_record_action()

    asyncio.run(node({"messages": [HumanMessage(content="")]}, runtime=runtime))

    assert calls == []


# --- AC4: a broken turn's retry, driven against the real graph -----------
#
# Everything above stubs `turn`/`resume`/`retry`/`thread_state` to prove
# dispatch alone. This one test drives the real compiled graph the way
# `test_service.py`/`test_narrate_seam.py` do, so the "roll not repeated,
# narration lands" half of AC4 rests on more than a stubbed call count.


@dataclass
class _RealGraphRun:
    status: str = "active"


class _RealGraphDb:
    """`load_context`'s own `ctx.db.execute(...)` path answers an empty
    result for every query, so `_build_game_context` gives up immediately
    -- this test is about the roll and the narration, not the context
    block."""

    def add(self, instance):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, instance):
        pass

    async def execute(self, statement):
        class _EmptyResult:
            def scalar_one_or_none(self):
                return None

            def scalars(self):
                return self

            def all(self):
                return []

        return _EmptyResult()


@dataclass
class _RealGraphRollSpy:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, db, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="roll-event-1",
            payload={
                "kind": kwargs["kind"],
                "actor_id": kwargs["actor_id"],
                "formula": "1d20+3",
                "faces": [17],
                "modifier": 3,
                "total": 20,
            },
        )


class _ScriptedCallModel:
    """`bind_tools()` is a no-op: the script already carries any tool
    calls. Each `.ainvoke()` consumes the next scripted item -- an
    `AIMessage` to return, or an exception to raise (the same shape
    `test_narrate_seam.py`'s own stand-in uses)."""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls = 0

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, prompt):
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


_ROLL_TOOL_CALL = AIMessage(
    content="",
    tool_calls=[
        {
            "id": "call-1",
            "name": "roll_dice",
            "args": {"kind": "ability_check", "context": {"ability": "dexterity"}},
        }
    ],
)


def test_a_broken_turn_retry_resumes_the_real_graph_without_repeating_the_roll(monkeypatch):
    """AC4: a turn that crashes in `narrate` right after a roll was made
    resumes, on `service.retry`, from that saved step: the roll is not
    made twice and a narration lands. Uses the real `service.turn`
    (which raises, exactly as `test_narrate_seam.py`'s own permanent-
    failure test does) and the real `service.retry` -- neither is
    stubbed here."""
    saver = InMemorySaver()

    @asynccontextmanager
    async def fake_checkpointer():
        yield saver

    monkeypatch.setattr(checkpointer_service, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(
        service, "load_prompt", lambda prompt_id, version=None: SimpleNamespace(text="Be the DM.")
    )

    event_calls: list[dict[str, Any]] = []

    async def fake_append_event(db, **kwargs):
        event_calls.append(kwargs)
        return SimpleNamespace(id="event-x", payload=kwargs.get("payload", {}))

    monkeypatch.setattr(nodes.playthrough_service, "append_event", fake_append_event)

    async def fake_get_campaign_run(db, *, user_id, run_id):
        return _RealGraphRun()

    monkeypatch.setattr(nodes.playthrough_service, "get_campaign_run", fake_get_campaign_run)

    roll_spy = _RealGraphRollSpy()
    monkeypatch.setattr(tools.playthrough_service, "roll", roll_spy)

    model = _ScriptedCallModel(
        [_ROLL_TOOL_CALL, LlmAuthError("bad key"), AIMessage(content="You leap clear of the pit.")]
    )
    agent = service.build_agent(model=model, checkpointer=saver)

    db = _RealGraphDb()
    context = DmContext(
        db=db, user_id="user-1", actor_id="actor-1", run_id="run-1", turn_id="turn-1"
    )

    with pytest.raises(LlmAuthError):
        asyncio.run(
            service.turn(agent, thread_id="run-1", context=context, player_text="I jump the pit.")
        )

    # The break landed right after the roll: exactly one roll so far, no
    # narration yet.
    assert len(roll_spy.calls) == 1
    assert [call["type"] for call in event_calls] == ["player_action"]

    snapshot = asyncio.run(service.thread_state(agent, thread_id="run-1"))
    assert snapshot.interrupt is None
    assert snapshot.pending is True

    result = asyncio.run(service.retry(agent, thread_id="run-1", context=context))

    assert result.reply == "You leap clear of the pit."
    assert len(roll_spy.calls) == 1  # the recorded roll is not repeated
    assert model.calls == 3
    assert [call["type"] for call in event_calls] == ["player_action", "narration"]
