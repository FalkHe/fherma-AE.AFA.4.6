"""Sprint 07 WI3 -- `app checkpoint ...` (binding interface, `research.md`
Interfaces; `app/core/checkpointer/commands.py`, registered in
`app/cli.py` as `cli.add_typer(checkpoint_app, name="checkpoint")`).

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/core/llm/test_commands.py`'s and
`tests/core/prompts/test_cli.py`'s style. Both seams this module touches are
faked: `checkpointer_service.checkpointer` (an async context manager, never
a real Postgres connection) and `demo_graph.start` / `demo_graph.resume`
(never the real LangGraph graph). No database, no engine, no real graph
execution - the interrupt/resume round trip itself is proven live, by hand
(research.md's "Live check"), not here."""

from contextlib import asynccontextmanager

from typer.testing import CliRunner

from app.cli import cli
from app.core.checkpointer import demo_graph
from app.core.checkpointer import service as checkpointer_service

runner = CliRunner()


@asynccontextmanager
async def _fake_checkpointer_cm():
    yield object()


def _patch_checkpointer(monkeypatch, calls: list | None = None):
    """Replace `checkpointer_service.checkpointer` with a fake async context
    manager that never opens a connection, recording each call (with no
    arguments - `checkpointer()` takes none) if `calls` is given."""

    def fake_checkpointer():
        if calls is not None:
            calls.append(True)
        return _fake_checkpointer_cm()

    monkeypatch.setattr(checkpointer_service, "checkpointer", fake_checkpointer)


def test_checkpoint_setup_command_exists_and_prints_the_contract_line(monkeypatch):
    calls = []

    async def fake_setup():
        calls.append(True)

    monkeypatch.setattr(checkpointer_service, "setup", fake_setup)

    result = runner.invoke(cli, ["checkpoint", "setup"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "checkpoints schema ready\n"
    assert calls == [True]


def test_checkpoint_setup_exits_1_with_the_failure_on_stderr_when_the_service_raises(
    monkeypatch,
):
    async def failing_setup():
        raise RuntimeError("could not reach postgres")

    monkeypatch.setattr(checkpointer_service, "setup", failing_setup)

    result = runner.invoke(cli, ["checkpoint", "setup"])

    assert result.exit_code == 1
    assert "could not reach postgres" in result.stderr
    assert result.stdout == ""


def test_demo_start_calls_the_service_and_graph_and_prints_the_interrupted_value(
    monkeypatch,
):
    checkpointer_calls = []
    _patch_checkpointer(monkeypatch, checkpointer_calls)
    start_calls = []

    async def fake_start(saver, thread_id):
        start_calls.append((saver, thread_id))
        return {"a": 1}

    monkeypatch.setattr(demo_graph, "start", fake_start)

    result = runner.invoke(cli, ["checkpoint", "demo", "start", "--thread", "demo-1"])

    assert result.exit_code == 0, result.stderr
    # `--thread`'s value reaches demo_graph.start() unchanged, via the
    # checkpointer the (faked) service produced.
    assert len(start_calls) == 1
    assert start_calls[0][1] == "demo-1"
    assert checkpointer_calls == [True]
    # The interrupt's value, JSON-encoded, behind the fixed "interrupted: "
    # prefix (I3) - a dict here to prove this isn't just `str(value)`.
    assert result.stdout == 'interrupted: {"a": 1}\n'


def test_demo_start_exits_1_when_the_graph_raises(monkeypatch):
    _patch_checkpointer(monkeypatch)

    async def failing_start(saver, thread_id):
        raise RuntimeError("the demo graph ran to completion without interrupting")

    monkeypatch.setattr(demo_graph, "start", failing_start)

    result = runner.invoke(cli, ["checkpoint", "demo", "start", "--thread", "demo-1"])

    assert result.exit_code == 1
    assert "without interrupting" in result.stderr
    assert result.stdout == ""


def test_demo_resume_calls_the_service_and_graph_and_prints_the_answer_line(monkeypatch):
    checkpointer_calls = []
    _patch_checkpointer(monkeypatch, checkpointer_calls)
    resume_calls = []

    async def fake_resume(saver, thread_id, value):
        resume_calls.append((saver, thread_id, value))
        # The left half is what a prior `start()` produced (not recomputed
        # here) - AC3's proof that the answer traces back to the first run.
        return f"hello-from-run-1|{value}"

    monkeypatch.setattr(demo_graph, "resume", fake_resume)

    result = runner.invoke(
        cli, ["checkpoint", "demo", "resume", "--thread", "demo-1", "--value", "hello"]
    )

    assert result.exit_code == 0, result.stderr
    assert len(resume_calls) == 1
    assert resume_calls[0][1] == "demo-1"
    assert resume_calls[0][2] == "hello"
    assert checkpointer_calls == [True]
    # Exact contract line (I3 / AC3): `answer: <left>|<value>`.
    assert result.stdout == "answer: hello-from-run-1|hello\n"


def test_demo_resume_fails_readably_when_the_thread_was_never_started(monkeypatch):
    # Exercises the real `demo_graph.resume` (not faked, unlike the other
    # resume tests) against a fake checkpointer whose `aget_tuple` reports
    # no prior checkpoint - the never-started-thread case - to prove the
    # CLI surfaces a plain sentence naming the thread rather than the bare
    # `KeyError` that node "one" would otherwise raise reading `state["seed"]`
    # off an empty state.
    class _FakeCheckpointer:
        async def aget_tuple(self, config):
            return None

    @asynccontextmanager
    async def _fake_cm():
        yield _FakeCheckpointer()

    monkeypatch.setattr(checkpointer_service, "checkpointer", lambda: _fake_cm())

    result = runner.invoke(
        cli,
        ["checkpoint", "demo", "resume", "--thread", "never-started", "--value", "x"],
    )

    assert result.exit_code == 1
    assert "never-started" in result.stderr
    assert "no interrupted state to resume" in result.stderr
    assert "KeyError" not in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == ""


def test_demo_resume_exits_1_when_the_graph_raises(monkeypatch):
    _patch_checkpointer(monkeypatch)

    async def failing_resume(saver, thread_id, value):
        raise RuntimeError("the demo graph did not produce an answer on resume")

    monkeypatch.setattr(demo_graph, "resume", failing_resume)

    result = runner.invoke(
        cli, ["checkpoint", "demo", "resume", "--thread", "demo-1", "--value", "hello"]
    )

    assert result.exit_code == 1
    assert "did not produce an answer" in result.stderr
    assert result.stdout == ""
