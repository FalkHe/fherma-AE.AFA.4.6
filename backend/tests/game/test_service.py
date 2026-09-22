"""The DM graph with a scripted model and a stubbed mechanic: the roll must
come from `playthrough.service.roll`, never from the model."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from typer.testing import CliRunner

from app.cli import cli
from app.core.checkpointer import service as checkpointer_service
from app.modules.game import commands, service
from app.modules.game.agent import nodes, tools
from app.modules.game.agent.state import DmContext

runner = CliRunner()


@dataclass
class _Prompt:
    text: str


@dataclass
class _Event:
    payload: dict[str, Any]
    id: str = "event-1"
    type: str = "roll"


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


class _ToolAwareFakeModel(GenericFakeChatModel):
    """`GenericFakeChatModel` raises `NotImplementedError` on `bind_tools`,
    which the narrate node calls; the script already carries the tool
    calls, so binding is a no-op here."""

    def bind_tools(self, tools, **kwargs):
        return self


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


class _FakeDb:
    def add(self, instance):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass


_DB = _FakeDb()
_CONTEXT = DmContext(db=_DB, user_id="user-1", actor_id="actor-1", run_id="run-1", turn_id="turn-1")


def _scripted_model(messages: list[AIMessage]) -> GenericFakeChatModel:
    return _ToolAwareFakeModel(messages=iter(messages))


def _turn(agent, text, thread_id="t1"):
    return asyncio.run(service.turn(agent, thread_id=thread_id, context=_CONTEXT, player_text=text))


@pytest.fixture(autouse=True)
def fake_checkpointer(monkeypatch):
    saver = InMemorySaver()

    @asynccontextmanager
    async def _fake_cm():
        yield saver

    monkeypatch.setattr(checkpointer_service, "checkpointer", _fake_cm)


@pytest.fixture
def prompt(monkeypatch):
    monkeypatch.setattr(
        service, "load_prompt", lambda prompt_id, version=None: _Prompt("Be the DM.")
    )


@pytest.fixture
def roll_spy(monkeypatch):
    spy = _RollSpy()
    monkeypatch.setattr(tools.playthrough_service, "roll", spy)
    return spy


@pytest.fixture(autouse=True)
def event_spy(monkeypatch):
    spy = _EventSpy()
    monkeypatch.setattr(nodes.playthrough_service, "append_event", spy)
    return spy


def test_turn_without_a_roll_returns_the_reply(prompt, roll_spy, event_spy):
    agent = service.build_agent(model=_scripted_model([AIMessage(content="You enter the tavern.")]))

    result = _turn(agent, "I walk in.")

    assert result.reply == "You enter the tavern."
    assert result.rolls == []
    assert roll_spy.calls == []
    assert len(event_spy.calls) == 2
    assert event_spy.calls[0]["type"] == "player_action"
    assert event_spy.calls[0]["payload"] == {"text": "I walk in."}
    assert event_spy.calls[0]["run_id"] == "run-1"
    assert event_spy.calls[0]["turn_id"] == "turn-1"
    assert event_spy.calls[1]["type"] == "narration"
    assert event_spy.calls[1]["payload"] == {"text": "You enter the tavern."}
    assert event_spy.calls[1]["run_id"] == "run-1"
    assert event_spy.calls[1]["turn_id"] == "turn-1"


def test_turn_routes_the_roll_through_the_playthrough_service(prompt, roll_spy):
    agent = service.build_agent(
        model=_scripted_model([_ROLL_CALL, AIMessage(content="You rolled 20 - the lock opens.")])
    )

    result = _turn(agent, "I pick the lock.")

    assert result.reply == "You rolled 20 - the lock opens."
    assert result.rolls == [
        {
            "roll_id": "event-1",
            "kind": "ability_check",
            "formula": "1d20+3",
            "faces": [17],
            "modifier": 3,
            "total": 20,
        }
    ]
    # The session, user, actor and turn come from the run context, never
    # from the model's arguments; the roll is always player-visible.
    assert roll_spy.calls == [
        {
            "db": _DB,
            "user_id": "user-1",
            "actor_id": "actor-1",
            "kind": "ability_check",
            "context": {"ability": "dexterity"},
            "visibility": "player",
            "turn_id": "turn-1",
        }
    ]


def test_turn_only_reports_rolls_from_the_current_turn(prompt, roll_spy):
    agent = service.build_agent(
        model=_scripted_model(
            [_ROLL_CALL, AIMessage(content="Open."), AIMessage(content="You step through.")]
        )
    )

    _turn(agent, "I pick the lock.")
    second = _turn(agent, "I go in.")

    assert second.reply == "You step through."
    assert second.rolls == []
    state = asyncio.run(agent.aget_state({"configurable": {"thread_id": "t1"}}))
    assert len(state.values["messages"]) == 6


def test_get_scene_tool_loads_scene_facts(prompt):
    scene_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-scene-1",
                "name": "get_scene",
                "args": {
                    "scene_id": "village-green",
                    "campaign_id": "greenhollow",
                    "version": "v1",
                },
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model([scene_call, AIMessage(content="You arrive at the Village Green.")])
    )
    result = _turn(agent, "Where am I?")
    assert result.reply == "You arrive at the Village Green."


def test_get_object_tool_loads_creature_or_item_by_id_or_name(prompt):
    creature_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-object-1",
                "name": "get_object",
                "args": {
                    "object_id": "Goblin Raider",
                    "campaign_id": "greenhollow",
                    "version": "v1",
                },
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model(
            [creature_call, AIMessage(content="The goblin raider snarls at you.")]
        )
    )
    result = _turn(agent, "What is that creature?")
    assert result.reply == "The goblin raider snarls at you."


def test_get_campaign_tool_loads_overview(prompt):
    campaign_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-campaign-1",
                "name": "get_campaign",
                "args": {"campaign_id": "greenhollow", "version": "v1"},
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model([campaign_call, AIMessage(content="Welcome to Greenhollow.")])
    )
    result = _turn(agent, "Tell me about this world.")
    assert result.reply == "Welcome to Greenhollow."


def test_content_tools_resolve_campaign_and_version_from_run(prompt, monkeypatch):
    @dataclass
    class _FakeCampaignRun:
        campaign_id: str = "greenhollow"
        content_version: str = "v1"

    async def fake_get_campaign_run(db, *, user_id, run_id):
        return _FakeCampaignRun()

    monkeypatch.setattr(tools.playthrough_service, "get_campaign_run", fake_get_campaign_run)

    scene_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-scene-2",
                "name": "get_scene",
                "args": {"scene_id": "thornway"},
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model(
            [scene_call, AIMessage(content="You see thorn bushes and a deer path.")]
        )
    )
    result = _turn(agent, "Look at the path.")
    assert result.reply == "You see thorn bushes and a deer path."


def test_get_object_not_found_handled_gracefully(prompt):
    object_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-object-2",
                "name": "get_object",
                "args": {
                    "object_id": "ancient-red-dragon",
                    "campaign_id": "greenhollow",
                    "version": "v1",
                },
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model(
            [
                object_call,
                AIMessage(content="There are no dragons here, only whispers in the wind."),
            ]
        )
    )
    result = _turn(agent, "Is there a dragon?")
    assert result.reply == "There are no dragons here, only whispers in the wind."


def test_resolve_check_tool_consumes_roll_and_evaluates_dc(prompt, monkeypatch):
    resolved_calls = []

    async def fake_resolve_check(db, *, user_id, roll_id, dc, turn_id=None):
        resolved_calls.append(
            {"user_id": user_id, "roll_id": roll_id, "dc": dc, "turn_id": turn_id}
        )
        return True

    monkeypatch.setattr(tools.playthrough_service, "resolve_check", fake_resolve_check)

    check_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-check-1",
                "name": "resolve_check",
                "args": {"roll_id": "roll-123", "dc": 15},
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model([check_call, AIMessage(content="You successfully clear the gap.")])
    )
    result = _turn(agent, "I jump across.")
    assert result.reply == "You successfully clear the gap."
    assert resolved_calls == [
        {"user_id": "user-1", "roll_id": "roll-123", "dc": 15, "turn_id": "turn-1"}
    ]


def test_resolve_save_tool_consumes_roll_and_evaluates_dc(prompt, monkeypatch):
    resolved_calls = []

    async def fake_resolve_save(db, *, user_id, roll_id, dc, turn_id=None):
        resolved_calls.append(
            {"user_id": user_id, "roll_id": roll_id, "dc": dc, "turn_id": turn_id}
        )
        return False

    monkeypatch.setattr(tools.playthrough_service, "resolve_save", fake_resolve_save)

    save_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-save-1",
                "name": "resolve_save",
                "args": {"roll_id": "roll-456", "dc": 18},
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model(
            [save_call, AIMessage(content="You fail to dodge the dragon breath.")]
        )
    )
    result = _turn(agent, "I try to dodge.")
    assert result.reply == "You fail to dodge the dragon breath."
    assert resolved_calls == [
        {"user_id": "user-1", "roll_id": "roll-456", "dc": 18, "turn_id": "turn-1"}
    ]


def test_passive_check_tool_evaluates_score_without_rolling(prompt, monkeypatch):
    passive_calls = []

    async def fake_passive_check(db, *, user_id, actor_id, ability, dc, turn_id=None):
        passive_calls.append(
            {
                "user_id": user_id,
                "actor_id": actor_id,
                "ability": ability,
                "dc": dc,
                "turn_id": turn_id,
            }
        )
        return True

    monkeypatch.setattr(tools.playthrough_service, "passive_check", fake_passive_check)

    passive_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-passive-1",
                "name": "passive_check",
                "args": {"ability": "wisdom", "dc": 12, "actor_id": "actor-1"},
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model([passive_call, AIMessage(content="You notice tracks in the mud.")])
    )
    result = _turn(agent, "Do I notice anything?")
    assert result.reply == "You notice tracks in the mud."
    assert passive_calls == [
        {
            "user_id": "user-1",
            "actor_id": "actor-1",
            "ability": "wisdom",
            "dc": 12,
            "turn_id": "turn-1",
        }
    ]


def test_roll_initiative_tool_rolls_both_sides(prompt, monkeypatch):
    initiative_calls = []

    async def fake_roll_initiative(db, *, user_id, side_a_ids, side_b_ids, turn_id=None):
        initiative_calls.append(
            {
                "user_id": user_id,
                "side_a_ids": side_a_ids,
                "side_b_ids": side_b_ids,
                "turn_id": turn_id,
            }
        )
        event_a = _Event(
            payload={"kind": "initiative", "total": 18, "formula": "1d20+2"},
            id="init-event-a",
            type="roll",
        )
        event_b = _Event(
            payload={"kind": "initiative", "total": 12, "formula": "1d20+1"},
            id="init-event-b",
            type="roll",
        )
        return event_a, event_b

    monkeypatch.setattr(tools.playthrough_service, "roll_initiative", fake_roll_initiative)

    init_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-init-1",
                "name": "roll_initiative",
                "args": {"side_a_ids": ["hero-1"], "side_b_ids": ["goblin-1"]},
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model([init_call, AIMessage(content="You act first!")])
    )
    result = _turn(agent, "Roll initiative.")
    assert result.reply == "You act first!"
    assert initiative_calls == [
        {
            "user_id": "user-1",
            "side_a_ids": ["hero-1"],
            "side_b_ids": ["goblin-1"],
            "turn_id": "turn-1",
        }
    ]


def test_the_model_cannot_supply_session_or_user_id():
    roll_schema = tools.roll_dice.tool_call_schema.model_json_schema()
    assert set(roll_schema["properties"]) == {"kind", "context", "actor_id"}

    check_schema = tools.resolve_check.tool_call_schema.model_json_schema()
    assert set(check_schema["properties"]) == {"roll_id", "dc"}

    save_schema = tools.resolve_save.tool_call_schema.model_json_schema()
    assert set(save_schema["properties"]) == {"roll_id", "dc"}

    passive_schema = tools.passive_check.tool_call_schema.model_json_schema()
    assert set(passive_schema["properties"]) == {"ability", "dc", "actor_id"}

    init_schema = tools.roll_initiative.tool_call_schema.model_json_schema()
    assert set(init_schema["properties"]) == {"side_a_ids", "side_b_ids"}


def test_the_model_can_supply_explicit_actor_id(prompt, roll_spy):
    roll_with_actor = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-2",
                "name": "roll_dice",
                "args": {
                    "kind": "ability_check",
                    "context": {"ability": "strength"},
                    "actor_id": "actor-2",
                },
            }
        ],
    )
    agent = service.build_agent(
        model=_scripted_model([roll_with_actor, AIMessage(content="Gimli smashes the door.")])
    )

    result = _turn(agent, "Gimli breaks the door down.")

    assert result.reply == "Gimli smashes the door."
    assert roll_spy.calls[-1]["actor_id"] == "actor-2"


def test_the_real_dm_prompt_names_the_tool_and_the_graph_has_all_nodes():
    agent = service.build_agent(model=_scripted_model([]))

    assert "roll_dice" in service.load_prompt(service.SYSTEM_PROMPT_ID).text
    assert set(agent.get_graph().nodes) >= {
        nodes.LOAD_CONTEXT,
        nodes.RECORD_ACTION,
        nodes.NARRATE,
        nodes.TOOLS_NODE,
        nodes.RECORD_NARRATION,
    }


def test_tool_failure_is_caught_and_narrated_without_crashing(monkeypatch, prompt):
    from app.modules.playthrough.dice import InvalidDiceExpressionError

    async def failing_roll(*args, **kwargs):
        raise InvalidDiceExpressionError("bad_formula")

    monkeypatch.setattr(tools.playthrough_service, "roll", failing_roll)

    scripted = _scripted_model(
        [
            _ROLL_CALL,
            AIMessage(content="The spell fizzles because the dice formula was invalid."),
        ]
    )
    agent = service.build_agent(model=scripted)

    result = _turn(agent, "Cast a spell with weird dice.")

    assert result.reply == "The spell fizzles because the dice formula was invalid."
    assert result.rolls == []


def test_cli_play_prints_reply_on_stdout_and_rolls_on_stderr(monkeypatch, prompt, roll_spy):
    scripted = _scripted_model([_ROLL_CALL, AIMessage(content="The lock opens.")])
    monkeypatch.setattr(service, "chat_model", lambda: scripted)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())

    result = runner.invoke(
        cli,
        ["game", "play", "--user", "user-1", "--actor", "actor-1", "--run-id", "run-1"],
        input="I pick the lock.\n",
    )

    assert result.exit_code == 0, result.output
    assert "The lock opens." in result.stdout
    assert "rolled ability_check 1d20+3: [17] +3 = 20" in result.stderr
    assert roll_spy.calls[0]["actor_id"] == "actor-1"
    assert roll_spy.calls[0]["user_id"] == "user-1"


def test_cli_play_loop_maintains_history_across_turns(monkeypatch, prompt):
    scripted = _scripted_model(
        [
            AIMessage(content="You see a dark hallway."),
            AIMessage(content="You step into the dark."),
        ]
    )
    monkeypatch.setattr(service, "chat_model", lambda: scripted)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())

    result = runner.invoke(
        cli,
        ["game", "play", "--user", "user-1", "--run-id", "run-1", "--thread-id", "test-thread"],
        input="look around\nwalk forward\n",
    )

    assert result.exit_code == 0, result.output
    assert "You see a dark hallway." in result.stdout
    assert "You step into the dark." in result.stdout


def test_cli_play_reports_a_missing_api_key_generically(monkeypatch, prompt):
    from app.core.llm.errors import LlmConfigurationError

    def boom():
        raise LlmConfigurationError()

    monkeypatch.setattr(service, "chat_model", boom)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())

    result = runner.invoke(
        cli,
        ["game", "play", "--user", "user-1"],
        input="hi\n",
    )

    assert result.exit_code == 1
    assert "OPENROUTER_API_KEY" in result.stderr


def test_cli_play_uses_checkpointer_from_service(monkeypatch, prompt):
    checkpointer_entered = []

    @asynccontextmanager
    async def tracking_checkpointer():
        saver = InMemorySaver()
        checkpointer_entered.append(True)
        yield saver

    monkeypatch.setattr(checkpointer_service, "checkpointer", tracking_checkpointer)
    scripted = _scripted_model([AIMessage(content="You see a gate.")])
    monkeypatch.setattr(service, "chat_model", lambda: scripted)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())

    result = runner.invoke(
        cli,
        ["game", "play", "--user", "user-1"],
        input="look\n",
    )

    assert result.exit_code == 0, result.output
    assert checkpointer_entered == [True]


def test_load_context_injects_scene_party_and_recap_into_system_prompt(monkeypatch, prompt):
    from app.modules.content.schemas import Exit, Scene
    from app.modules.playthrough.models import CampaignRun, GameObject
    from app.modules.playthrough.schemas import NarrationRead

    captured_inputs = []

    class _CaptureModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        async def ainvoke(self, input, **kwargs):
            captured_inputs.append(input)
            return AIMessage(content="The adventure continues.")

    class _QueryResult:
        def __init__(self, scalar=None, scalars_list=None):
            self._scalar = scalar
            self._scalars_list = scalars_list or []

        def scalar_one_or_none(self):
            return self._scalar

        def scalars(self):
            return self

        def all(self):
            return self._scalars_list

    char = GameObject(
        id="char-1",
        name="Rosalind",
        current_hp=15,
        max_hp=15,
        armour_class=16,
        is_alive=True,
        kind="creature",
        member_id="mem-1",
        scene_id="tavern-room",
        campaign_run_id="run-1",
        instance_key="char-1",
    )
    monster = GameObject(
        id="gob-1",
        name="Goblin Lookout",
        current_hp=6,
        max_hp=6,
        armour_class=13,
        is_alive=True,
        kind="creature",
        member_id=None,
        scene_id="tavern-room",
        campaign_run_id="run-1",
        instance_key="gob-1",
    )
    fixture = GameObject(
        id="chest-1",
        name="Oak Chest",
        kind="fixture",
        member_id=None,
        scene_id="tavern-room",
        campaign_run_id="run-1",
        instance_key="chest-1",
    )

    execute_queries = [
        _QueryResult(
            scalar=CampaignRun(id="run-1", campaign_id="greenhollow", content_version="v1")
        ),
        _QueryResult(scalars_list=[char]),
        _QueryResult(scalars_list=["Shortsword", "Healing Potion"]),
        _QueryResult(scalars_list=[monster, fixture]),
    ]
    query_idx = 0

    class _ExecutableDb:
        async def execute(self, statement):
            nonlocal query_idx
            if query_idx < len(execute_queries):
                res = execute_queries[query_idx]
                query_idx += 1
                return res
            return _QueryResult()

        async def commit(self):
            pass

    scene = Scene(
        id="tavern-room",
        title="The Old Boar Tavern",
        truth=["A warm fireplace flickers against stone walls.", "The barkeep is pouring ale."],
        npc_intent="Keep the peace and serve drinks",
        exits=[
            Exit(
                id="cellar-door",
                kind="scene",
                to="cellar",
                description="a wooden trapdoor to the cellar",
            )
        ],
    )
    monkeypatch.setattr(nodes.content_service, "load_scene", lambda cid, ver, sid: scene)

    async def fake_awaiting(db, *, user_id, run_id):
        return "roll:ability_check:dexterity"

    async def fake_recap(db, *, run_id, n=5):
        return [
            NarrationRead(
                id="n1",
                text="You arrived at the tavern in the dead of night.",
                created_at="2026-09-22T00:00:00Z",
            )
        ]

    monkeypatch.setattr(nodes.playthrough_service, "get_awaiting", fake_awaiting)
    monkeypatch.setattr(nodes.playthrough_service, "recap", fake_recap)

    ctx = DmContext(db=_ExecutableDb(), user_id="user-1", run_id="run-1", actor_id="char-1")
    agent = service.build_agent(model=_CaptureModel(messages=iter([])))

    res = asyncio.run(
        service.turn(
            agent, thread_id="t-cold", context=ctx, player_text="I look around the tavern."
        )
    )
    assert res.reply == "The adventure continues."

    assert len(captured_inputs) > 0
    system_msg = captured_inputs[0][0]
    content = system_msg.content

    assert "## Current Game Context" in content
    assert "The Old Boar Tavern" in content
    assert "A warm fireplace flickers against stone walls." in content
    assert "Keep the peace and serve drinks" in content
    assert "cellar-door (a wooden trapdoor to the cellar) -> cellar" in content
    assert (
        "Rosalind (id: char-1): HP 15/15, AC 16, status: alive, "
        "carried items: [Shortsword, Healing Potion]"
    ) in content
    assert "Goblin Lookout (id: gob-1, HP: 6/6, AC: 13)" in content
    assert "Oak Chest (id: chest-1, kind: fixture)" in content
    assert "### Awaiting\n- roll:ability_check:dexterity" in content
    assert "You arrived at the tavern in the dead of night." in content


class _FakeSessionmaker:
    def __call__(self):
        return self

    async def __aenter__(self):
        return _DB

    async def __aexit__(self, *exc):
        return False
