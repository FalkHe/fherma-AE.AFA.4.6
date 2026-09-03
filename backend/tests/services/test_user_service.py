"""`app/services/user_service.py` — registration, auth, role/password admin ops.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.
"""

import asyncio

import pytest

from app.db.models.user import UserRole
from app.services import session_service, user_service
from app.services.user_service import UsernameTakenError, UserNotFoundError
from tests.services.conftest import FakeAsyncSession


def test_normalize_username_strips_and_lowercases() -> None:
    assert user_service.normalize_username(" Alice ") == "alice"
    assert user_service.normalize_username("Foo.Bar_1-2") == "foo.bar_1-2"


def test_register_stores_normalized_username_and_default_role(
    fake_session: FakeAsyncSession,
) -> None:
    user = asyncio.run(user_service.register(fake_session, " Alice ", "password123"))

    assert user.username == "alice"
    assert user.role is UserRole.USER
    assert user.id is not None
    assert fake_session.commit_count == 1
    # The stored value is a hash, never the plaintext password.
    assert user.password_hash != "password123"


def test_register_duplicate_normalized_username_raises(fake_session: FakeAsyncSession) -> None:
    asyncio.run(user_service.register(fake_session, "alice", "password123"))

    with pytest.raises(UsernameTakenError):
        asyncio.run(user_service.register(fake_session, " ALICE ", "another-pw"))


def test_authenticate_normalizes_username_and_succeeds(fake_session: FakeAsyncSession) -> None:
    asyncio.run(user_service.register(fake_session, "Alice", "password123"))

    user = asyncio.run(user_service.authenticate(fake_session, " ALICE ", "password123"))

    assert user is not None
    assert user.username == "alice"


def test_authenticate_wrong_password_returns_none(fake_session: FakeAsyncSession) -> None:
    asyncio.run(user_service.register(fake_session, "alice", "password123"))

    user = asyncio.run(user_service.authenticate(fake_session, "alice", "wrong-password"))

    assert user is None


def test_authenticate_unknown_user_returns_none(fake_session: FakeAsyncSession) -> None:
    user = asyncio.run(user_service.authenticate(fake_session, "ghost", "irrelevant"))

    assert user is None


def test_authenticate_unknown_user_exercises_dummy_hash_constant_time_path(
    fake_session: FakeAsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    real_verify = user_service.password_hash.verify

    def spy_verify(password: str, hash_: str) -> bool:
        calls.append((password, hash_))
        return real_verify(password, hash_)

    monkeypatch.setattr(user_service.password_hash, "verify", spy_verify)

    user = asyncio.run(user_service.authenticate(fake_session, "ghost", "irrelevant"))

    assert user is None
    assert calls == [("irrelevant", user_service._DUMMY_HASH)]


def test_set_role_promotion_does_not_revoke_sessions(fake_session: FakeAsyncSession) -> None:
    user = asyncio.run(user_service.register(fake_session, "alice", "password123"))
    asyncio.run(session_service.create_session(fake_session, user.id))
    assert len(fake_session.sessions) == 1

    updated = asyncio.run(user_service.set_role(fake_session, "alice", UserRole.ADMIN))

    assert updated.role is UserRole.ADMIN
    assert len(fake_session.sessions) == 1


def test_set_role_demotion_revokes_all_sessions(fake_session: FakeAsyncSession) -> None:
    user = asyncio.run(user_service.register(fake_session, "alice", "password123"))
    asyncio.run(user_service.set_role(fake_session, "alice", UserRole.ADMIN))
    asyncio.run(session_service.create_session(fake_session, user.id))
    asyncio.run(session_service.create_session(fake_session, user.id, remember_me=True))
    assert len(fake_session.sessions) == 2

    updated = asyncio.run(user_service.set_role(fake_session, "alice", UserRole.USER))

    assert updated.role is UserRole.USER
    assert len(fake_session.sessions) == 0


def test_set_role_is_idempotent_and_does_not_revoke(fake_session: FakeAsyncSession) -> None:
    user = asyncio.run(user_service.register(fake_session, "alice", "password123"))
    asyncio.run(session_service.create_session(fake_session, user.id))

    updated = asyncio.run(user_service.set_role(fake_session, "alice", UserRole.USER))

    assert updated.role is UserRole.USER
    assert len(fake_session.sessions) == 1


def test_set_role_unknown_user_raises(fake_session: FakeAsyncSession) -> None:
    with pytest.raises(UserNotFoundError):
        asyncio.run(user_service.set_role(fake_session, "ghost", UserRole.ADMIN))


def test_reset_password_rehashes_and_revokes_all_sessions(fake_session: FakeAsyncSession) -> None:
    user = asyncio.run(user_service.register(fake_session, "alice", "old-password"))
    asyncio.run(session_service.create_session(fake_session, user.id))
    asyncio.run(session_service.create_session(fake_session, user.id))
    assert len(fake_session.sessions) == 2

    asyncio.run(user_service.reset_password(fake_session, "alice", "new-password"))

    assert len(fake_session.sessions) == 0
    assert asyncio.run(user_service.authenticate(fake_session, "alice", "old-password")) is None
    new_login = asyncio.run(user_service.authenticate(fake_session, "alice", "new-password"))
    assert new_login is not None


def test_reset_password_unknown_user_raises(fake_session: FakeAsyncSession) -> None:
    with pytest.raises(UserNotFoundError):
        asyncio.run(user_service.reset_password(fake_session, "ghost", "new-password"))
