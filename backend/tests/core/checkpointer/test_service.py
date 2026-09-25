"""Sprint 07 WI1 — `app/core/checkpointer/service.py`: `checkpointer_conn_string`
(← research.md Interfaces).

`checkpointer_conn_string` is a pure function; the bulk of this file is its
coverage. `checkpointer()`, `ensure_schema()` and `setup()` each open a real
Postgres connection in production, which `backend/tests/conftest.py` forbids
the suite from ever doing - so those three are covered here against fakes
substituted for `psycopg.AsyncConnection.connect` and
`AsyncPostgresSaver.from_conn_string` instead, never a live database
(research.md's "Live check" remains the end-to-end proof). The fakes are
themselves coroutine functions / `@asynccontextmanager`s, matching the real
APIs' shape exactly - a plain function standing in for a coroutine function
would pass even when the code under test forgot an `await`, which is the bug
this suite exists to catch."""

import asyncio
from contextlib import asynccontextmanager

from app.core.checkpointer import service
from app.core.checkpointer.schema import CHECKPOINTER_SCHEMA
from app.core.checkpointer.service import checkpointer_conn_string


def test_strips_the_driver_tag_and_pins_search_path_to_the_checkpointer_schema():
    """The example pinned exactly by the sprint's interface contract."""
    assert (
        checkpointer_conn_string("postgresql+psycopg://app:app@postgres:5432/application")
        == "postgresql://app:app@postgres:5432/application?options=-csearch_path%3Dcheckpoints"
    )


def test_leaves_a_url_with_no_driver_tag_unchanged_besides_the_added_query():
    assert (
        checkpointer_conn_string("postgresql://app:app@postgres:5432/application")
        == "postgresql://app:app@postgres:5432/application?options=-csearch_path%3Dcheckpoints"
    )


def test_preserves_existing_query_parameters_ahead_of_options():
    assert (
        checkpointer_conn_string(
            "postgresql+psycopg://app:app@postgres:5432/application?sslmode=require"
        )
        == "postgresql://app:app@postgres:5432/application"
        "?sslmode=require&options=-csearch_path%3Dcheckpoints"
    )


def test_passes_a_password_with_special_characters_through_untouched():
    """The netloc (user:pass@host:port) is never re-parsed or re-encoded -
    only the scheme is trimmed and the query rebuilt - so an already-escaped
    password survives byte-for-byte."""
    assert (
        checkpointer_conn_string("postgresql+psycopg://app:p%40ss%3Aword@postgres:5432/application")
        == "postgresql://app:p%40ss%3Aword@postgres:5432/application"
        "?options=-csearch_path%3Dcheckpoints"
    )


def test_escapes_the_inner_equals_sign_in_the_options_value():
    """`%3D`, not a literal `=` - a second, unescaped `=` inside the query
    string's `options` value would parse as a second key, which is what
    `psycopg.ProgrammingError: missing "=" after ...` (research.md) comes
    from getting this wrong."""
    conn_string = checkpointer_conn_string("postgresql+psycopg://app:app@postgres:5432/application")
    assert "-csearch_path%3Dcheckpoints" in conn_string
    assert "-csearch_path=checkpoints" not in conn_string


class _StubAsyncConnection:
    """Fake `psycopg.AsyncConnection` - only what `ensure_schema()` touches:
    the async-context-manager protocol and `execute()`."""

    def __init__(self) -> None:
        self.executed: list[str] = []

    async def execute(self, sql: str) -> None:
        self.executed.append(sql)

    async def __aenter__(self) -> "_StubAsyncConnection":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


def test_ensure_schema_awaits_connect_before_entering_it_as_a_context_manager(monkeypatch):
    """`psycopg.AsyncConnection.connect` is a coroutine function, so the fake
    here is one too (`async def`, not a plain function) - substituting a
    plain function would let a missing `await` slip through unnoticed. This
    is the exact shape that let the real bug (`ensure_schema()` doing `async
    with psycopg.AsyncConnection.connect(...)` without awaiting the call
    first) through review: verified red against the pre-fix line, raising
    `TypeError: 'coroutine' object does not support the asynchronous context
    manager protocol`, because the coroutine this fake returns was never
    awaited."""
    stub_conn = _StubAsyncConnection()

    async def fake_connect(conn_string: str) -> _StubAsyncConnection:
        return stub_conn

    monkeypatch.setattr(service.psycopg.AsyncConnection, "connect", fake_connect)

    asyncio.run(service.ensure_schema())

    assert stub_conn.executed == [f"CREATE SCHEMA IF NOT EXISTS {CHECKPOINTER_SCHEMA}"]


def test_checkpointer_enters_from_conn_string_without_awaiting_the_call(monkeypatch):
    """`AsyncPostgresSaver.from_conn_string` is itself `@asynccontextmanager`-
    decorated: calling it returns an async context manager directly, not a
    coroutine - so `checkpointer()` must pass it straight through, never
    `await` the call itself. The fake mirrors that exact shape, so an
    accidental `await AsyncPostgresSaver.from_conn_string(...)` in
    `checkpointer()` would fail this test the same way the `ensure_schema()`
    bug failed its own."""
    sentinel_saver = object()

    @asynccontextmanager
    async def fake_from_conn_string(conn_string: str, *, serde=None):
        yield sentinel_saver

    monkeypatch.setattr(service.AsyncPostgresSaver, "from_conn_string", fake_from_conn_string)

    async def _run() -> object:
        async with service.checkpointer() as saver:
            return saver

    assert asyncio.run(_run()) is sentinel_saver


def test_setup_awaits_ensure_schema_then_the_saver_setup_in_order(monkeypatch):
    """`setup()` wraps two more calls the same way `ensure_schema()` wrapped
    `AsyncConnection.connect`: `await ensure_schema()`, then `async with
    checkpointer() as saver: await saver.setup()`. Both fakes are coroutine
    functions / an `@asynccontextmanager`, so a missing `await` on either
    would leave `calls` incomplete or out of order instead of silently
    passing."""
    calls: list[str] = []

    async def fake_ensure_schema() -> None:
        calls.append("ensure_schema")

    class _StubSaver:
        async def setup(self) -> None:
            calls.append("saver.setup")

    @asynccontextmanager
    async def fake_checkpointer():
        yield _StubSaver()

    monkeypatch.setattr(service, "ensure_schema", fake_ensure_schema)
    monkeypatch.setattr(service, "checkpointer", fake_checkpointer)

    asyncio.run(service.setup())

    assert calls == ["ensure_schema", "saver.setup"]
