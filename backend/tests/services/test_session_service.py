"""`app/services/session_service.py` — token issuance, resolution, revocation.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py`; every
async service call is driven through `asyncio.run()` per the project's
"no pytest-asyncio" convention.
"""

import asyncio
import hashlib
import re
from datetime import UTC, datetime, timedelta

from app.db.models.session import Session
from app.db.models.user import User, UserRole
from app.services import session_service
from tests.services.conftest import FakeAsyncSession

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def test_ttl_constants_are_pinned() -> None:
    assert timedelta(hours=24) == session_service.SESSION_TTL
    assert timedelta(days=30) == session_service.REMEMBER_ME_TTL


def test_hash_token_is_sha256_hex() -> None:
    digest = session_service.hash_token("some-raw-token")

    assert digest == hashlib.sha256(b"some-raw-token").hexdigest()
    assert _HEX_64.match(digest)


def test_create_session_returns_raw_token_never_persisted(fake_session: FakeAsyncSession) -> None:
    raw_token, row = asyncio.run(session_service.create_session(fake_session, "user-1"))

    assert raw_token != row.token_hash
    assert row.token_hash == session_service.hash_token(raw_token)
    assert len(row.token_hash) == 64
    # The raw token appears nowhere on the persisted row.
    assert raw_token not in vars(row).values()
    assert fake_session.commit_count == 1


def test_create_session_default_ttl_is_session_ttl(fake_session: FakeAsyncSession) -> None:
    before = datetime.now(UTC)
    _, row = asyncio.run(session_service.create_session(fake_session, "user-1", remember_me=False))
    after = datetime.now(UTC)

    assert row.remember_me is False
    expected_low = before + session_service.SESSION_TTL
    expected_high = after + session_service.SESSION_TTL
    assert expected_low <= row.expires_at <= expected_high


def test_create_session_remember_me_uses_remember_me_ttl(fake_session: FakeAsyncSession) -> None:
    before = datetime.now(UTC)
    _, row = asyncio.run(session_service.create_session(fake_session, "user-1", remember_me=True))
    after = datetime.now(UTC)

    assert row.remember_me is True
    expected_low = before + session_service.REMEMBER_ME_TTL
    expected_high = after + session_service.REMEMBER_ME_TTL
    assert expected_low <= row.expires_at <= expected_high


def test_resolve_session_returns_user_for_valid_token(fake_session: FakeAsyncSession) -> None:
    user = User(username="alice", password_hash="hash", role=UserRole.USER)
    fake_session.add(user)
    raw_token, _ = asyncio.run(session_service.create_session(fake_session, user.id))

    resolved = asyncio.run(session_service.resolve_session(fake_session, raw_token))

    assert resolved is not None
    assert resolved.id == user.id


def test_resolve_session_unknown_token_returns_none(fake_session: FakeAsyncSession) -> None:
    resolved = asyncio.run(session_service.resolve_session(fake_session, "not-a-real-token"))

    assert resolved is None


def test_resolve_session_deletes_expired_row_and_returns_none(
    fake_session: FakeAsyncSession,
) -> None:
    raw_token = "expired-raw-token"
    expired_row = Session(
        user_id="user-1",
        token_hash=session_service.hash_token(raw_token),
        remember_me=False,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    fake_session.add(expired_row)
    assert len(fake_session.sessions) == 1

    resolved = asyncio.run(session_service.resolve_session(fake_session, raw_token))

    assert resolved is None
    assert len(fake_session.sessions) == 0


def test_resolve_session_does_not_extend_expiry(fake_session: FakeAsyncSession) -> None:
    user = User(username="alice", password_hash="hash", role=UserRole.USER)
    fake_session.add(user)
    raw_token, row = asyncio.run(session_service.create_session(fake_session, user.id))
    expires_before = row.expires_at

    asyncio.run(session_service.resolve_session(fake_session, raw_token))

    assert row.expires_at == expires_before


def test_resolve_session_loads_user_fresh_not_a_cached_reference(
    fake_session: FakeAsyncSession,
) -> None:
    user = User(id="user-1", username="alice", password_hash="hash", role=UserRole.USER)
    fake_session.add(user)
    raw_token, _ = asyncio.run(session_service.create_session(fake_session, user.id))

    # Simulate a role change made through a different object/request: replace
    # the stored row outright rather than mutating the one we already hold.
    promoted = User(id="user-1", username="alice", password_hash="hash", role=UserRole.ADMIN)
    fake_session.users["user-1"] = promoted

    resolved = asyncio.run(session_service.resolve_session(fake_session, raw_token))

    assert resolved is promoted
    assert resolved.role is UserRole.ADMIN


def test_revoke_by_token_deletes_matching_session(fake_session: FakeAsyncSession) -> None:
    raw_token, _ = asyncio.run(session_service.create_session(fake_session, "user-1"))
    assert len(fake_session.sessions) == 1

    asyncio.run(session_service.revoke_by_token(fake_session, raw_token))

    assert len(fake_session.sessions) == 0


def test_revoke_by_token_unknown_token_is_a_noop(fake_session: FakeAsyncSession) -> None:
    asyncio.run(session_service.create_session(fake_session, "user-1"))
    assert len(fake_session.sessions) == 1

    asyncio.run(session_service.revoke_by_token(fake_session, "no-such-token"))

    assert len(fake_session.sessions) == 1


def test_revoke_all_for_user_only_deletes_that_users_sessions(
    fake_session: FakeAsyncSession,
) -> None:
    asyncio.run(session_service.create_session(fake_session, "user-1"))
    asyncio.run(session_service.create_session(fake_session, "user-1"))
    asyncio.run(session_service.create_session(fake_session, "user-2"))

    asyncio.run(session_service.revoke_all_for_user(fake_session, "user-1"))

    remaining = list(fake_session.sessions.values())
    assert len(remaining) == 1
    assert remaining[0].user_id == "user-2"
    assert fake_session.commit_count == 4  # 3 creates + 1 revoke


def test_delete_all_for_user_does_not_commit(fake_session: FakeAsyncSession) -> None:
    asyncio.run(session_service.create_session(fake_session, "user-1"))
    commits_after_create = fake_session.commit_count

    asyncio.run(session_service.delete_all_for_user(fake_session, "user-1"))

    assert fake_session.commit_count == commits_after_create
    assert len(fake_session.sessions) == 0
