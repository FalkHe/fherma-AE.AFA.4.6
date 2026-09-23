"""WI2 (sprint 010/01): `app game play` resolves the acting hero from the
signed-in player and the run instead of requiring `--actor`, and keys the
checkpointer thread to the run id so a session can be quit and rejoined
where it stopped.

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/playthrough/test_commands.py`'s style. The
actor-resolution and thread-id tests fake `commands._play_session` itself
(module attribute) so they exercise only `play`'s own argument-resolution
logic, never the graph; the seam for the hero lookup is
`playthrough_service.get_member_character` (module attribute, per this
sprint's dependency), never a name import.

The replay test (AC2) is the exception: it runs the real agent end to end
across two separate `play` invocations sharing one `InMemorySaver`
checkpointer, the same way `tests/game/test_service.py`'s CLI tests do, to
prove the checkpointer thread -- not any new resume code -- is what makes
the second invocation find the first one's pending question.
"""

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
from app.modules.game import commands
from app.modules.game import service as game_service
from app.modules.game.agent import nodes, tools
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CharacterNotFoundError
from app.modules.users import service as users_service

runner = CliRunner()

RUN_ID = "run-1"
USER_ID = "user-1"


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


_DB = _FakeDb()


class _FakeSessionmaker:
    def __call__(self):
        return self

    async def __aenter__(self):
        return _DB

    async def __aexit__(self, *exc):
        return False


@dataclass
class _Character:
    id: str


@dataclass
class _User:
    id: str


@dataclass
class _PlaySessionSpy:
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, *, user_id, run_id, actor_id, thread_id):
        self.calls.append(
            {
                "user_id": user_id,
                "run_id": run_id,
                "actor_id": actor_id,
                "thread_id": thread_id,
            }
        )


def _invoke(args: list[str], *, input: str | None = None) -> Any:
    return runner.invoke(cli, args, input=input)


@pytest.fixture(autouse=True)
def stub_user_lookup(monkeypatch):
    async def fake_get_user_by_username(db, *, username):
        return _User(id=USER_ID)

    monkeypatch.setattr(users_service, "get_user_by_username", fake_get_user_by_username)


# --- actor resolution (AC1) --------------------------------------------


def test_username_resolves_the_user_before_starting_play(monkeypatch):
    username_calls = []

    async def fake_get_user_by_username(db, *, username):
        username_calls.append(username)
        return _User(id=USER_ID)

    monkeypatch.setattr(users_service, "get_user_by_username", fake_get_user_by_username)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    spy = _PlaySessionSpy()
    monkeypatch.setattr(commands, "_play_session", spy)

    result = _invoke(["game", "play", "--user", "  ALICE  ", "--actor", "actor-1"])

    assert result.exit_code == 0, result.output
    assert username_calls == ["  ALICE  "]
    assert spy.calls[0]["user_id"] == USER_ID


def test_unknown_username_exits_2_without_starting_play(monkeypatch):
    async def fake_get_user_by_username(db, *, username):
        return None

    monkeypatch.setattr(users_service, "get_user_by_username", fake_get_user_by_username)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    spy = _PlaySessionSpy()
    monkeypatch.setattr(commands, "_play_session", spy)

    result = _invoke(["game", "play", "--user", "missing", "--actor", "actor-1"])

    assert result.exit_code == 2
    assert spy.calls == []
    assert "Invalid value for --user: unknown username: missing" in result.output


def test_run_id_alone_resolves_the_seated_hero_and_starts_play(monkeypatch):
    calls = []

    async def fake_get_member_character(db, *, user_id, run_id):
        calls.append({"user_id": user_id, "run_id": run_id})
        return _Character(id="hero-1")

    monkeypatch.setattr(playthrough_service, "get_member_character", fake_get_member_character)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    spy = _PlaySessionSpy()
    monkeypatch.setattr(commands, "_play_session", spy)

    result = _invoke(["game", "play", "--user", USER_ID, "--run-id", RUN_ID])

    assert result.exit_code == 0, result.output
    assert calls == [{"user_id": USER_ID, "run_id": RUN_ID}]
    assert spy.calls == [
        {"user_id": USER_ID, "run_id": RUN_ID, "actor_id": "hero-1", "thread_id": RUN_ID}
    ]


def test_actor_option_overrides_and_skips_resolution(monkeypatch):
    async def failing_get_member_character(db, *, user_id, run_id):
        raise AssertionError("get_member_character should not be called when --actor is given")

    monkeypatch.setattr(playthrough_service, "get_member_character", failing_get_member_character)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    spy = _PlaySessionSpy()
    monkeypatch.setattr(commands, "_play_session", spy)

    result = _invoke(
        ["game", "play", "--user", USER_ID, "--run-id", RUN_ID, "--actor", "actor-override"]
    )

    assert result.exit_code == 0, result.output
    assert spy.calls == [
        {
            "user_id": USER_ID,
            "run_id": RUN_ID,
            "actor_id": "actor-override",
            "thread_id": RUN_ID,
        }
    ]


def test_a_run_where_the_player_has_no_character_exits_1_with_the_errors_message(monkeypatch):
    async def fake_get_member_character(db, *, user_id, run_id):
        raise CharacterNotFoundError(run_id)

    monkeypatch.setattr(playthrough_service, "get_member_character", fake_get_member_character)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    spy = _PlaySessionSpy()
    monkeypatch.setattr(commands, "_play_session", spy)

    result = _invoke(["game", "play", "--user", USER_ID, "--run-id", RUN_ID])

    assert result.exit_code == 1
    assert spy.calls == []
    assert result.stderr.strip() == str(CharacterNotFoundError(RUN_ID))


# --- thread id defaulting -------------------------------------------------


def test_thread_id_defaults_to_the_run_id(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    spy = _PlaySessionSpy()
    monkeypatch.setattr(commands, "_play_session", spy)

    result = _invoke(["game", "play", "--user", USER_ID, "--run-id", RUN_ID, "--actor", "actor-1"])

    assert result.exit_code == 0, result.output
    assert spy.calls[0]["thread_id"] == RUN_ID


def test_thread_id_option_still_overrides_the_run_id(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    spy = _PlaySessionSpy()
    monkeypatch.setattr(commands, "_play_session", spy)

    result = _invoke(
        [
            "game",
            "play",
            "--user",
            USER_ID,
            "--run-id",
            RUN_ID,
            "--actor",
            "actor-1",
            "--thread-id",
            "custom-thread",
        ]
    )

    assert result.exit_code == 0, result.output
    assert spy.calls[0]["thread_id"] == "custom-thread"


# --- quit and rejoin (AC2) ------------------------------------------------


class _ToolAwareFakeModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_a_session_quit_while_the_dm_waits_for_an_answer_still_has_it_waiting_on_replay(
    monkeypatch,
):
    saver = InMemorySaver()

    @asynccontextmanager
    async def fake_checkpointer():
        yield saver

    monkeypatch.setattr(checkpointer_service, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(
        game_service, "load_prompt", lambda prompt_id, version=None: _Prompt("Be the DM.")
    )
    monkeypatch.setattr(nodes.playthrough_service, "append_event", _noop_append_event)
    monkeypatch.setattr(nodes.playthrough_service, "get_campaign_run", _noop_get_campaign_run)
    monkeypatch.setattr(nodes.playthrough_service, "activate_campaign_run", _noop_get_campaign_run)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())

    ask_call = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call-ask-1",
                "name": "ask_player",
                "args": {"text": "Do you sneak or run?", "options": ["Sneak", "Run"]},
            }
        ],
    )

    async def fake_ask_player(db, *, user_id, run_id, text, options, turn_id=None):
        return _Event(id="q-event-1", type="question", payload={"text": text, "options": options})

    monkeypatch.setattr(tools.playthrough_service, "ask_player", fake_ask_player)

    first_model = _ToolAwareFakeModel(messages=iter([ask_call]))
    monkeypatch.setattr(game_service, "chat_model", lambda: first_model)

    first_result = _invoke(
        [
            "game",
            "play",
            "--user",
            USER_ID,
            "--run-id",
            RUN_ID,
            "--actor",
            "actor-1",
        ],
        input="I approach the goblins.\n",
    )
    # No answer supplied: input stream ends while the DM is waiting, quitting
    # the session with the question still pending.
    assert first_result.exit_code == 0, first_result.output
    assert "Do you sneak or run?" in first_result.stdout

    second_model = _ToolAwareFakeModel(
        messages=iter([AIMessage(content="You choose to sneak quietly.")])
    )
    monkeypatch.setattr(game_service, "chat_model", lambda: second_model)

    second_result = _invoke(
        [
            "game",
            "play",
            "--user",
            USER_ID,
            "--run-id",
            RUN_ID,
            "--actor",
            "actor-1",
        ],
        input="1\n",
    )

    assert second_result.exit_code == 0, second_result.output
    # The same question is still waiting -- rejoining the run alone (same
    # thread id) surfaces it again without a fresh player message.
    assert "Do you sneak or run?" in second_result.stdout
    assert "You choose to sneak quietly." in second_result.stdout


@dataclass
class _Prompt:
    text: str


@dataclass
class _Event:
    id: str
    type: str
    payload: dict[str, Any]
    campaign_run_id: str = RUN_ID


async def _noop_append_event(db, **kwargs):
    return _Event(
        id="event-1",
        type=kwargs.get("type", "narration"),
        payload=kwargs.get("payload", {}),
    )


class _Run:
    status = "active"


async def _noop_get_campaign_run(db, **kwargs):
    return _Run()
