"""The narration node's model call goes through `core/llm/service.ainvoke_chat`
(sprint 010-02, WI2), so a turn gets the same quiet retry and error
classification every other model call already has, and its narration
carries the turn's summed token counts and cost.

`_ScriptedCallModel` stands in for the DM's bound model: `bind_tools()` is a
no-op (the script already carries any tool calls) and `.ainvoke()` consumes
the next scripted item -- an `AIMessage` to return, or an exception to
raise. `retry._asleep` is monkeypatched so a retried turn never really
sleeps.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver

from app.core.checkpointer import service as checkpointer_service
from app.core.llm import retry as llm_retry
from app.core.llm.errors import LlmAuthError, LlmUnavailableError
from app.modules.game import service
from app.modules.game.agent import nodes, tools
from app.modules.game.agent.state import DmContext


@dataclass
class _Prompt:
    text: str


@dataclass
class _Event:
    payload: dict[str, Any]
    id: str = "event-1"
    type: str = "roll"
    campaign_run_id: str = "run-1"


@dataclass
class _RollSpy:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, db, **kwargs):
        self.calls.append({"db": db, **kwargs})
        return _Event(
            {
                "kind": kwargs["kind"],
                "actor_id": kwargs["actor_id"],
                "formula": "1d20+3",
                "faces": [17],
                "modifier": 3,
                "total": 20,
            }
        )


@dataclass
class _EventSpy:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, db, **kwargs):
        self.calls.append({"db": db, **kwargs})
        return _Event(kwargs)


@dataclass
class _Run:
    status: str = "active"


@dataclass
class _GetCampaignRunSpy:
    status: str = "active"

    async def __call__(self, db, **kwargs):
        return _Run(status=self.status)


@dataclass
class _ActivateCampaignRunSpy:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, db, **kwargs):
        self.calls.append({"db": db, **kwargs})
        return _Run(status="active")


class _FakeDb:
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


class _ScriptedCallModel:
    """`bind_tools()` is a no-op: the script already carries any tool
    calls. Each `.ainvoke()` consumes the next scripted item."""

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


_DB = _FakeDb()
_CONTEXT = DmContext(db=_DB, user_id="user-1", actor_id="actor-1", run_id="run-1", turn_id="turn-1")

_ROLL_CALL = AIMessage(
    content="",
    tool_calls=[
        {
            "id": "call-1",
            "name": "roll_dice",
            "args": {"kind": "ability_check", "context": {"ability": "dexterity"}},
        }
    ],
)


def _turn(agent, text, thread_id="t1"):
    return asyncio.run(service.turn(agent, thread_id=thread_id, context=_CONTEXT, player_text=text))


@pytest.fixture(autouse=True)
def fake_checkpointer(monkeypatch):
    saver = InMemorySaver()

    @asynccontextmanager
    async def _fake_cm():
        yield saver

    monkeypatch.setattr(checkpointer_service, "checkpointer", _fake_cm)


@pytest.fixture(autouse=True)
def prompt(monkeypatch):
    monkeypatch.setattr(
        service, "load_prompt", lambda prompt_id, version=None: _Prompt("Be the DM.")
    )


@pytest.fixture(autouse=True)
def event_spy(monkeypatch):
    spy = _EventSpy()
    monkeypatch.setattr(nodes.playthrough_service, "append_event", spy)
    return spy


@pytest.fixture(autouse=True)
def get_campaign_run_spy(monkeypatch):
    spy = _GetCampaignRunSpy()
    monkeypatch.setattr(nodes.playthrough_service, "get_campaign_run", spy)
    return spy


@pytest.fixture(autouse=True)
def activate_campaign_run_spy(monkeypatch):
    spy = _ActivateCampaignRunSpy()
    monkeypatch.setattr(nodes.playthrough_service, "activate_campaign_run", spy)
    return spy


@pytest.fixture
def roll_spy(monkeypatch):
    spy = _RollSpy()
    monkeypatch.setattr(tools.playthrough_service, "roll", spy)
    return spy


@pytest.fixture(autouse=True)
def no_real_asleep(monkeypatch):
    async def _noop(seconds):
        return None

    monkeypatch.setattr(llm_retry, "_asleep", _noop)


def _usage_message(*, prompt_tokens, completion_tokens, cost_usd, text="", tool_calls=None):
    return AIMessage(
        content=text,
        tool_calls=tool_calls or [],
        usage_metadata={
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        response_metadata={"cost": cost_usd, "finish_reason": "stop"},
    )


# --- AC3: a retryable failure is quiet ---------------------------------


def test_a_retryable_model_failure_still_ends_the_turn_in_a_narration():
    model = _ScriptedCallModel(
        [LlmUnavailableError("502"), AIMessage(content="You enter the tavern.")]
    )
    agent = service.build_agent(model=model)

    result = _turn(agent, "I walk in.")

    assert result.reply == "You enter the tavern."
    assert model.calls == 2


# --- AC4: a permanent failure raises, prior work stays recorded ---------


def test_a_permanent_model_failure_raises_with_prior_events_still_recorded(roll_spy, event_spy):
    model = _ScriptedCallModel([_ROLL_CALL, LlmAuthError("bad key")])
    agent = service.build_agent(model=model)

    with pytest.raises(LlmAuthError):
        _turn(agent, "I pick the lock.")

    # The player's action was recorded, and the roll the first model call
    # asked for already ran (and, in production, already committed) --
    # neither is undone by the narrate node raising afterwards.
    assert [call["type"] for call in event_spy.calls] == ["player_action"]
    assert len(roll_spy.calls) == 1
    assert model.calls == 2


# --- AC1/AC2: narration carries the turn's summed usage ------------------


def test_a_turn_with_two_model_calls_sums_tokens_and_cost_on_the_narration(roll_spy):
    model = _ScriptedCallModel(
        [
            _usage_message(
                prompt_tokens=100,
                completion_tokens=10,
                cost_usd=0.001,
                tool_calls=[
                    {
                        "id": "call-1",
                        "name": "roll_dice",
                        "args": {"kind": "ability_check", "context": {"ability": "dexterity"}},
                    }
                ],
            ),
            _usage_message(
                prompt_tokens=150,
                completion_tokens=40,
                cost_usd=0.002,
                text="You rolled 20 - the lock opens.",
            ),
        ]
    )
    agent = service.build_agent(model=model)

    result = _turn(agent, "I pick the lock.")

    assert result.reply == "You rolled 20 - the lock opens."
    narration_calls = [
        call for call in nodes.playthrough_service.append_event.calls if call["type"] == "narration"
    ]
    assert len(narration_calls) == 1
    usage = narration_calls[0]["usage"]
    assert usage.prompt_tokens == 250
    assert usage.completion_tokens == 50
    assert usage.total_tokens == 300
    assert usage.cost_usd == pytest.approx(0.003)
    assert usage.cost_usd > 0


def test_several_turns_usage_sums_to_the_total_across_the_run():
    first_model = _ScriptedCallModel(
        [_usage_message(prompt_tokens=10, completion_tokens=5, cost_usd=0.001, text="First.")]
    )
    agent_one = service.build_agent(model=first_model)
    first_result = _turn(agent_one, "Look around.", thread_id="turn-a")
    first_usage = [
        call["usage"]
        for call in nodes.playthrough_service.append_event.calls
        if call["type"] == "narration"
    ][-1]

    second_model = _ScriptedCallModel(
        [_usage_message(prompt_tokens=20, completion_tokens=8, cost_usd=0.002, text="Second.")]
    )
    agent_two = service.build_agent(model=second_model)
    second_result = _turn(agent_two, "Move on.", thread_id="turn-b")
    second_usage = [
        call["usage"]
        for call in nodes.playthrough_service.append_event.calls
        if call["type"] == "narration"
    ][-1]

    assert first_result.reply == "First."
    assert second_result.reply == "Second."

    total_prompt_tokens = first_usage.prompt_tokens + second_usage.prompt_tokens
    total_completion_tokens = first_usage.completion_tokens + second_usage.completion_tokens
    total_cost = first_usage.cost_usd + second_usage.cost_usd

    assert total_prompt_tokens == 30
    assert total_completion_tokens == 13
    assert total_cost == pytest.approx(0.003)


def test_a_call_with_no_reported_cost_leaves_the_turn_cost_none():
    no_cost_message = AIMessage(
        content="Quiet.",
        usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10},
        response_metadata={"finish_reason": "stop"},
    )
    model = _ScriptedCallModel([no_cost_message])
    agent = service.build_agent(model=model)

    _turn(agent, "Listen.")

    narration_calls = [
        call for call in nodes.playthrough_service.append_event.calls if call["type"] == "narration"
    ]
    usage = narration_calls[0]["usage"]
    assert usage.total_tokens == 10
    assert usage.cost_usd is None
