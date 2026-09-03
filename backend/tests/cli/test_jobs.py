"""Tests for `app jobs ping` and for the broker's import safety.

Nothing here talks to Redis: importing `app.jobs.broker` may only build a lazy
connection pool (the pinned `REDIS_URL` in the top-level conftest is never
listening), and the CLI test replaces the broker and the task's kicker with
in-memory stubs.
"""

from typing import Any

import pytest
from typer.testing import CliRunner

from app.cli.main import app as cli
from app.jobs import TransientJobError
from app.jobs.broker import broker

runner = CliRunner()

STUB_TASK_ID = "0" * 32


class _StubTask:
    """Stand-in for the `TaskiqTask` returned by `.kiq()`."""

    task_id = STUB_TASK_ID


class _StubKicker:
    """Records `.kiq()` calls instead of pushing them onto Redis."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def kiq(self, *args: Any, **kwargs: Any) -> _StubTask:
        self.calls.append((args, kwargs))
        return _StubTask()


class _StubBroker:
    """Counts the broker's connection lifecycle calls."""

    def __init__(self) -> None:
        self.startups = 0
        self.shutdowns = 0

    async def startup(self) -> None:
        self.startups += 1

    async def shutdown(self) -> None:
        self.shutdowns += 1


@pytest.fixture
def stub_kicker(monkeypatch: pytest.MonkeyPatch) -> _StubKicker:
    kicker = _StubKicker()
    monkeypatch.setattr("app.cli.jobs.demo_ping", kicker)
    return kicker


@pytest.fixture(autouse=True)
def stub_broker(monkeypatch: pytest.MonkeyPatch) -> _StubBroker:
    stub = _StubBroker()
    monkeypatch.setattr("app.cli.jobs.broker", stub)
    return stub


def test_ping_enqueues_the_task_and_reports_its_id(
    stub_kicker: _StubKicker, stub_broker: _StubBroker
) -> None:
    result = runner.invoke(cli, ["jobs", "ping"])

    assert result.exit_code == 0, result.output
    assert f"Enqueued demo.ping as {STUB_TASK_ID}." in result.stdout
    assert stub_kicker.calls == [(("pong",), {})]
    assert (stub_broker.startups, stub_broker.shutdowns) == (1, 1)


def test_ping_passes_the_message_argument_through(stub_kicker: _StubKicker) -> None:
    result = runner.invoke(cli, ["jobs", "ping", "hello"])

    assert result.exit_code == 0, result.output
    assert stub_kicker.calls == [(("hello",), {})]


def test_broker_is_importable_without_redis_and_retries_only_transient_errors() -> None:
    middleware = next(m for m in broker.middlewares if type(m).__name__ == "SmartRetryMiddleware")

    assert list(middleware.types_of_exceptions) == [TransientJobError]
