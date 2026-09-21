"""Shared fake for the sprint-01 LLM acceptance tests: a stand-in for
`langchain_openrouter.ChatOpenRouter`, monkeypatched onto
`app.core.llm.service.ChatOpenRouter` per the sprint's binding interface I1
("`ChatOpenRouter` is a module-level name — monkeypatch `service.ChatOpenRouter`
to capture kwargs without a key").

`test_service.py` (AC3) and `test_commands.py` (AC2, AC4, AC5) both drive the
real `chat_model(...)` / `app llm chat` code paths and fake out only this one
network-touching class, so the fake needs to look like a LangChain chat model
*class*: callers construct it, then call `.invoke(prompt)` or
`.stream(prompt)` on the instance.

Originally held no import of `app.core.llm` at module scope, back when that
package did not exist yet (sprint 01 was building it): a conftest-level
import failure would have taken every test under `tests/core/` down with
it, not just the llm ones. The package is real now (sprints 01-03), so
sprint 03 adds one module-scope import of its own, `retry` - for the
autouse fixture below, not for anything test-module-specific.
"""

import pytest
import structlog

from app.core.llm import retry as llm_retry


@pytest.fixture(autouse=True)
def _reset_structlog_after_every_test():
    """Guards every test in this directory against a cross-test structlog
    leak, not just the ones that call `configure_logging()` themselves.

    `app.cli.cli`'s callback calls `configure_logging()` on every
    `CliRunner.invoke(cli, ...)` (`test_commands.py`'s own sprint-01 tests,
    unconditionally); none of those reset it afterward, since before sprint
    03 nothing on the `chat()`/`chat_stream()` failure path ever logged
    anything, so the leak was inert. `configure_logging()` binds structlog's
    `PrintLoggerFactory` to *that test's* `capsys`-provided `sys.stderr`
    object, which pytest closes at teardown - sprint 03's `retry.py` logs on
    every failed attempt (← AC4), on a path exercised across most of this
    directory's test modules, so a later test's log call can otherwise hit
    the now-closed stream (`ValueError: I/O operation on closed file`) or
    silently write to a stale one. Resetting after *every* test, not just
    the ones that configure logging on purpose, is the only reliable fix -
    the leak can originate in any test that happens to invoke the real CLI
    callback."""
    yield
    structlog.reset_defaults()


@pytest.fixture(autouse=True)
def _never_really_sleep(monkeypatch):
    """Safety net for every test in this directory, not just the ones that
    explicitly stub the delay themselves (qa's own `sleep_calls` fixture in
    `test_retry.py`): `chat()`/`chat_stream()` now retry underneath almost
    every failure path exercised here (← sprint 03), so any test that
    forgets to mock `retry._sleep` pays for a real backoff delay instead of
    the intended instant one - a single forgotten mock can turn a
    millisecond test into a multi-second one without ever failing outright,
    which is easy to miss.

    Records into `.calls` rather than a bare no-op, so the seam stays
    inspectable through this fixture too; a test that wants to assert on
    the delays still overrides `retry._sleep` itself (`monkeypatch.setattr`
    stacks - the later call wins for that test, and both revert cleanly, in
    reverse order, at teardown)."""
    calls: list[float] = []
    monkeypatch.setattr(llm_retry, "_sleep", calls.append)
    return calls


@pytest.fixture
def recording_chat_open_router():
    """A fresh fake `ChatOpenRouter` class per test. `.calls` records every
    constructor call's kwargs; `.response` / `.chunks` script what
    `.invoke()` / `.stream()` hand back."""

    class _RecordingChatOpenRouter:
        calls: list[dict] = []
        configs: list = []
        response = None
        chunks: list = []

        def __init__(self, *args, **kwargs):
            type(self).calls.append(kwargs)

        # `.configs` records the `config=` the seam passes through - the
        # run name and, with tracing on, the Langfuse callback handler.
        def invoke(self, prompt, config=None):
            type(self).configs.append(config)
            return type(self).response

        def stream(self, prompt, config=None):
            type(self).configs.append(config)
            yield from type(self).chunks

    return _RecordingChatOpenRouter
