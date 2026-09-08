"""§8 criteria 21-22: GET /api/v1/users/me.

`require_auth` lives in `app.modules.auth.dependencies` (its own contract
test is `tests/auth/test_dependencies.py`), but the route itself is
`users.routes.read_current_user`, so its request/response contract is tested
here per the one-to-one module mirror (D1).
"""

import uuid

from app.modules.auth import service as auth_service
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

USER_ID = uuid.uuid4()


def test_read_current_user_returns_200_with_user_and_csrf_header(
    client, monkeypatch, session_cookie_header
):
    session = make_session(user_id=USER_ID, csrf_token="the-current-csrf-token")
    user = make_user(user_id=USER_ID, username="aragorn")

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)

    response = client.get("/api/v1/users/me", headers=session_cookie_header("a-valid-cookie"))

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "aragorn"
    assert body["id"] == str(user.id)
    assert response.headers["x-csrf-token"] == "the-current-csrf-token"


def test_read_current_user_without_cookie_returns_401_not_authenticated(client, monkeypatch):
    resolve_calls = []

    async def fake_resolve_session(db, *, token):
        resolve_calls.append(token)
        return make_session(user_id=USER_ID)

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)

    response = client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    # §6.1: an absent cookie must not even call resolve_session.
    assert resolve_calls == []


def test_read_current_user_with_unknown_cookie_returns_401_session_expired_and_clears_cookie(
    client, monkeypatch, session_cookie_header
):
    async def fake_resolve_session(db, *, token):
        return None

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)

    response = client.get(
        "/api/v1/users/me",
        headers=session_cookie_header("syntactically-valid-but-unknown-token"),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith("session=")
    assert "Max-Age=0" in set_cookie


def test_read_current_user_orphaned_session_row_returns_401_session_expired(
    client, monkeypatch, session_cookie_header
):
    """§6.1: `require_auth`'s second query (the user, by the session's
    `user_id`) returning `None` - an orphaned session row - is also
    SESSION_EXPIRED. Not independently numbered in §8, but pinned as part of
    the exact contract QA is told to stub against, and worth a dedicated
    case: it is the one branch that is invisible if only the first query is
    ever exercised."""
    session = make_session(user_id=USER_ID)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return None

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)

    response = client.get("/api/v1/users/me", headers=session_cookie_header("a-valid-cookie"))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"
