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

The replay test (AC2) is the exception (sprint 011/08, WI2): it monkeypatches
`game_service.run_turn` and `playthrough_service.list_events` across two
separate `play` invocations to prove `_play_session` renders whatever
`awaiting` says and rejoins where it left off -- the real graph's own
checkpointed replay is `test_scenarios_database.py`'s job, not this CLI
wiring test's.
"""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from app.cli import cli
from app.modules.game import commands
from app.modules.game import service as game_service
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


def test_turn_output_prefixes_narration_and_tool_results(monkeypatch):
    output = []

    def fake_echo(message, *, err=False):
        output.append((message, err))

    monkeypatch.setattr(commands.typer, "echo", fake_echo)

    commands._print_turn_result(
        game_service.TurnResult(
            reply="The goblin ducks behind a crate.",
            rolls=[
                {
                    "kind": "attack",
                    "formula": "1d20+4",
                    "faces": [17],
                    "modifier": 4,
                    "total": 21,
                }
            ],
        )
    )

    assert output == [
        ("* rolled attack 1d20+4: [17] +4 = 21", True),
        ("< The goblin ducks behind a crate.", False),
    ]


# --- quit and rejoin (AC2) ------------------------------------------------


@dataclass
class _Event:
    id: str
    type: str
    payload: dict[str, Any]
    campaign_run_id: str = RUN_ID
    actor_member_id: str | None = None
    turn_id: str | None = None
    visibility: str = "player"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: Any = None
    created_at: Any = None


@dataclass
class _Outcome:
    turn_id: str
    kind: str
    awaiting: str


async def _noop_record_narration(db, **kwargs):
    return _Event(id="event-2", type="narration", payload={"text": kwargs.get("text", "")})


def test_events_resolves_latest_run_id_when_omitted(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    monkeypatch.setattr(
        playthrough_service,
        "get_latest_campaign_run_id",
        lambda db: asyncio.sleep(0, "latest-run-123"),
    )
    monkeypatch.setattr(playthrough_service, "get_run", lambda db, run_id: asyncio.sleep(0, None))

    fake_events = [
        _Event(
            id="ev-1",
            type="narration",
            visibility="player",
            payload={"text": "Welcome to the dungeon."},
            campaign_run_id="latest-run-123",
        ),
        _Event(
            id="ev-2",
            type="tool_call",
            visibility="dm",
            payload={
                "name": "inspect_object",
                "args": {"instance_key": "chest"},
                "result": "locked",
            },
            campaign_run_id="latest-run-123",
        ),
    ]
    monkeypatch.setattr(
        playthrough_service,
        "list_all_events",
        lambda db, run_id, after_id=None, limit=None: asyncio.sleep(0, fake_events),
    )

    result = runner.invoke(cli, ["game", "events"])

    assert result.exit_code == 0, result.output
    assert "run: latest-run-123" in result.stdout
    assert "[NARRATION] Welcome to the dungeon." in result.stdout
    assert "[TOOL:DM] inspect_object({'instance_key': 'chest'}) -> locked" in result.stdout


def test_events_with_explicit_run_id(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    monkeypatch.setattr(playthrough_service, "get_run", lambda db, run_id: asyncio.sleep(0, None))
    monkeypatch.setattr(
        playthrough_service,
        "list_all_events",
        lambda db, run_id, after_id=None, limit=None: asyncio.sleep(0, []),
    )

    result = runner.invoke(cli, ["game", "events", "explicit-run-999"])

    assert result.exit_code == 0, result.output
    assert "run: explicit-run-999" in result.stdout


def test_events_exits_1_when_no_runs_exist(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    monkeypatch.setattr(
        playthrough_service, "get_latest_campaign_run_id", lambda db: asyncio.sleep(0, None)
    )

    result = runner.invoke(cli, ["game", "events"])

    assert result.exit_code == 1
    assert "No campaign runs found." in result.stderr


def test_events_verbose_json_output(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    monkeypatch.setattr(playthrough_service, "get_run", lambda db, run_id: asyncio.sleep(0, None))
    fake_events = [
        _Event(
            id="ev-1",
            type="narration",
            visibility="player",
            payload={"text": "A dark cave opens up."},
            campaign_run_id=RUN_ID,
        )
    ]
    monkeypatch.setattr(
        playthrough_service,
        "list_all_events",
        lambda db, run_id, after_id=None, limit=None: asyncio.sleep(0, fake_events),
    )

    result = runner.invoke(cli, ["game", "events", RUN_ID, "-v"])

    assert result.exit_code == 0, result.output
    assert "run: run-1" in result.stdout
    assert '"id": "ev-1"' in result.stdout
    assert '"type": "narration"' in result.stdout
    assert '"text": "A dark cave opens up."' in result.stdout


def test_events_follow_mode_polls_and_prints_new_events(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    monkeypatch.setattr(playthrough_service, "get_run", lambda db, run_id: asyncio.sleep(0, None))
    monkeypatch.setattr(
        playthrough_service, "get_latest_event_id", lambda db, run_id: asyncio.sleep(0, "ev-0")
    )

    calls = 0

    async def fake_list_all_events(db, *, run_id, after_id=None, limit=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [
                _Event(
                    id="ev-1",
                    type="player_action",
                    visibility="player",
                    payload={"text": "I open the door."},
                    campaign_run_id=run_id,
                )
            ]
        raise KeyboardInterrupt()

    monkeypatch.setattr(playthrough_service, "list_all_events", fake_list_all_events)

    result = runner.invoke(cli, ["game", "events", RUN_ID, "-f"])

    assert result.exit_code == 0, result.output
    assert "run: run-1" in result.stdout
    assert "[PLAYER] I open the door." in result.stdout


def test_actions_prints_checkpoint_history_in_chronological_order(monkeypatch):
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())
    monkeypatch.setattr(
        playthrough_service,
        "get_latest_campaign_run_id",
        lambda db: asyncio.sleep(0, RUN_ID),
    )

    snapshots = [
        SimpleNamespace(
            config={"configurable": {"checkpoint_id": "cp-2"}},
            created_at=None,
            metadata={"step": 2, "source": "loop", "writes": {"narrate": {"messages": ["reply"]}}},
            next=("narrate",),
            values={},
            tasks=(),
            parent_config=None,
        ),
        SimpleNamespace(
            config={"configurable": {"checkpoint_id": "cp-1"}},
            created_at=None,
            metadata={"step": 1, "source": "loop", "writes": {"advance": {}}},
            next=("execute",),
            values={},
            tasks=(),
            parent_config=None,
        ),
    ]

    class _Agent:
        async def _history(self, config, *, limit=None):
            for snapshot in snapshots:
                yield snapshot

        def aget_state_history(self, config, *, limit=None):
            return self._history(config, limit=limit)

    @asynccontextmanager
    async def fake_checkpointer():
        yield object()

    monkeypatch.setattr(commands.checkpointer_service, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(commands.game_service, "build_agent", lambda **kwargs: _Agent())

    result = runner.invoke(cli, ["game", "actions"])

    assert result.exit_code == 0, result.output
    assert "thread: run-1" in result.stdout
    assert result.stdout.index("[cp-1]") < result.stdout.index("[cp-2]")
    assert '"narrate"' in result.stdout


def test_actions_verbose_includes_pending_interrupts(monkeypatch):
    snapshots = [
        SimpleNamespace(
            config={"configurable": {"checkpoint_id": "cp-9"}},
            created_at=None,
            metadata={"step": 9, "source": "loop", "writes": {}},
            next=("narrate",),
            values={"messages": []},
            tasks=(
                SimpleNamespace(
                    name="narrate",
                    interrupts=(SimpleNamespace(value={"type": "question"}),),
                    error=None,
                ),
            ),
            parent_config=None,
        )
    ]

    class _Agent:
        async def _history(self, config, *, limit=None):
            for snapshot in snapshots:
                yield snapshot

        def aget_state_history(self, config, *, limit=None):
            return self._history(config, limit=limit)

    @asynccontextmanager
    async def fake_checkpointer():
        yield object()

    monkeypatch.setattr(commands.checkpointer_service, "checkpointer", fake_checkpointer)
    monkeypatch.setattr(commands.game_service, "build_agent", lambda **kwargs: _Agent())

    result = runner.invoke(cli, ["game", "actions", RUN_ID, "--verbose", "--limit", "1"])

    assert result.exit_code == 0, result.output
    assert '"checkpoint": "cp-9"' in result.stdout
    assert '"type": "question"' in result.stdout


def test_a_session_quit_while_the_dm_waits_for_an_answer_still_has_it_waiting_on_replay(
    monkeypatch,
):
    question_event = _Event(
        id="q-event-1",
        type="question",
        payload={"text": "Do you sneak or run?", "options": ["Sneak", "Run"]},
    )

    async def fake_get_member_character(db, *, user_id, run_id):
        return _Character(id="actor-1")

    monkeypatch.setattr(playthrough_service, "get_member_character", fake_get_member_character)
    monkeypatch.setattr(commands, "get_sessionmaker", lambda: _FakeSessionmaker())

    # First invocation: the run's own turn engine leaves the question
    # pending -- no answer is supplied before the input stream ends, quitting
    # the session with it still waiting.
    async def fake_run_turn_first(db, *, user_id, run_id, text):
        return _Outcome(turn_id="turn-1", kind="action", awaiting="answer:q-event-1")

    async def fake_list_events_first(db, *, user_id, run_id, after=None):
        return [question_event]

    monkeypatch.setattr(game_service, "run_turn", fake_run_turn_first)
    monkeypatch.setattr(playthrough_service, "list_events", fake_list_events_first)

    first_result = _invoke(
        ["game", "play", "--user", USER_ID, "--run-id", RUN_ID],
        input="I approach the goblins.\n",
    )
    assert first_result.exit_code == 0, first_result.output
    assert "Do you sneak or run?" in first_result.stdout

    # Second invocation, same run: rejoining alone (no fresh player message
    # is sent for the opening call) surfaces the same still-pending question.
    async def fake_run_turn_second(db, *, user_id, run_id, text):
        if text is None:
            return _Outcome(turn_id="turn-1", kind="action", awaiting="answer:q-event-1")
        return _Outcome(turn_id="turn-1", kind="answer", awaiting="none")

    calls = []

    async def fake_list_events_second(db, *, user_id, run_id, after=None):
        calls.append(after)
        if len(calls) == 1:
            return [question_event]
        return [
            _Event(
                id="n-event-1",
                type="narration",
                payload={"text": "You choose to sneak quietly."},
            )
        ]

    monkeypatch.setattr(game_service, "run_turn", fake_run_turn_second)
    monkeypatch.setattr(playthrough_service, "list_events", fake_list_events_second)

    second_result = _invoke(
        ["game", "play", "--user", USER_ID, "--run-id", RUN_ID],
        input="1\n",
    )

    assert second_result.exit_code == 0, second_result.output
    assert "Do you sneak or run?" in second_result.stdout
    assert "You choose to sneak quietly." in second_result.stdout
