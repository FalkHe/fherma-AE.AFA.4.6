"""Tests for `app users set-role` / `app users reset-password`.

`app.cli.users` opens a session via `get_sessionmaker()()` and hands it to
`user_service`. Rather than stub the service itself, these tests monkeypatch
`get_sessionmaker` to hand out the same in-memory `FakeAsyncSession` used by
`tests/services/test_user_service.py` (via `tests/services/conftest.py`), so
the real service logic (normalisation, session revocation) runs end to end
through the CLI without ever opening a database engine.
"""

import asyncio

import pytest
from typer.testing import CliRunner

from app.cli.main import app as cli
from app.db.models.user import UserRole
from app.services import session_service, user_service
from tests.services.conftest import FakeAsyncSession

runner = CliRunner()


class _SessionContextManager:
    """Adapts a `FakeAsyncSession` to the `async with sessionmaker() as s:` shape."""

    def __init__(self, session: FakeAsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> FakeAsyncSession:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture(autouse=True)
def _patch_sessionmaker(monkeypatch: pytest.MonkeyPatch, fake_session: FakeAsyncSession) -> None:
    """Point `app.cli.users.get_sessionmaker()()` at the in-memory fake session.

    Patched on the CLI module (not `app.db.session`) so a real engine is never
    constructed, mirroring how routes get a stub session in the top-level
    `conftest.py`.
    """
    monkeypatch.setattr(
        "app.cli.users.get_sessionmaker",
        lambda: lambda: _SessionContextManager(fake_session),
    )


# --- set-role ----------------------------------------------------------------


def test_set_role_promotes_user_and_exits_zero(fake_session: FakeAsyncSession) -> None:
    asyncio.run(user_service.register(fake_session, "alice", "password123"))

    result = runner.invoke(cli, ["users", "set-role", "alice", "admin"])

    assert result.exit_code == 0, result.output
    assert "alice now has role admin." in result.stdout
    stored = next(iter(fake_session.users.values()))
    assert stored.role is UserRole.ADMIN


def test_set_role_rerun_is_idempotent(fake_session: FakeAsyncSession) -> None:
    asyncio.run(user_service.register(fake_session, "alice", "password123"))
    first = runner.invoke(cli, ["users", "set-role", "alice", "admin"])
    assert first.exit_code == 0, first.output

    second = runner.invoke(cli, ["users", "set-role", "alice", "admin"])

    assert second.exit_code == 0, second.output
    assert "alice now has role admin." in second.stdout


def test_set_role_unknown_user_exits_one_with_message_on_stderr(
    fake_session: FakeAsyncSession,
) -> None:
    result = runner.invoke(cli, ["users", "set-role", "ghost", "admin"])

    assert result.exit_code == 1
    assert "ghost" in result.stderr
    assert result.stdout == ""


def test_set_role_invalid_role_is_rejected_by_typer_without_reaching_service(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    async def _spy_set_role(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("service must not be called for an invalid role choice")

    monkeypatch.setattr(user_service, "set_role", _spy_set_role)

    result = runner.invoke(cli, ["users", "set-role", "alice", "superuser"])

    assert result.exit_code != 0
    assert calls == []


# --- reset-password ------------------------------------------------------------


def test_reset_password_uses_hidden_confirmed_prompt_and_exits_zero(
    fake_session: FakeAsyncSession,
) -> None:
    asyncio.run(user_service.register(fake_session, "alice", "old-password"))
    asyncio.run(session_service.create_session(fake_session, next(iter(fake_session.users))))
    assert len(fake_session.sessions) == 1

    result = runner.invoke(
        cli,
        ["users", "reset-password", "alice"],
        input="new-password123\nnew-password123\n",
    )

    assert result.exit_code == 0, result.output
    assert "Password for alice reset; all sessions revoked." in result.stdout
    # Hidden prompt: the typed password is never echoed back.
    assert "new-password123" not in result.output
    assert len(fake_session.sessions) == 0
    assert asyncio.run(user_service.authenticate(fake_session, "alice", "old-password")) is None
    assert (
        asyncio.run(user_service.authenticate(fake_session, "alice", "new-password123")) is not None
    )


def test_reset_password_mismatched_confirmation_fails_without_reaching_service(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[object] = []

    async def _spy_reset_password(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(user_service, "reset_password", _spy_reset_password)

    result = runner.invoke(
        cli,
        ["users", "reset-password", "alice"],
        input="password-one\npassword-two\n",
    )

    assert result.exit_code != 0
    assert calls == []


def test_reset_password_unknown_user_exits_one_with_message_on_stderr(
    fake_session: FakeAsyncSession,
) -> None:
    result = runner.invoke(
        cli,
        ["users", "reset-password", "ghost"],
        input="new-password123\nnew-password123\n",
    )

    assert result.exit_code == 1
    assert "ghost" in result.stderr
