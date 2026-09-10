"""§8 criteria 23-25: POST /api/v1/auth/sign-out."""

from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

USER_ID = generate_id()
VALID_TOKEN = "a-valid-session-cookie-value"  # noqa: S105
CSRF_TOKEN = "the-matching-csrf-token"  # noqa: S105


def _stub_valid_session(monkeypatch):
    session = make_session(user_id=USER_ID, csrf_token=CSRF_TOKEN)
    user = make_user(user_id=USER_ID)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


def test_sign_out_returns_204_clears_the_cookie_and_the_session_stops_working(
    client, monkeypatch, session_cookie_header
):
    session = make_session(user_id=USER_ID, csrf_token=CSRF_TOKEN)
    user = make_user(user_id=USER_ID)
    revoked_tokens: set[str] = set()

    async def fake_resolve_session(db, *, token):
        return None if token in revoked_tokens else session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    async def fake_delete_session(db, *, token):
        revoked_tokens.add(token)

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)
    monkeypatch.setattr(auth_service, "delete_session", fake_delete_session)

    response = client.post(
        "/api/v1/auth/sign-out",
        headers={**session_cookie_header(VALID_TOKEN), "X-CSRF-Token": CSRF_TOKEN},
    )

    assert response.status_code == 204
    assert response.content == b""
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith("session=")
    assert "Max-Age=0" in set_cookie

    stale = client.get("/api/v1/users/me", headers=session_cookie_header(VALID_TOKEN))
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "SESSION_EXPIRED"


def test_sign_out_missing_csrf_header_returns_403(client, monkeypatch, session_cookie_header):
    _stub_valid_session(monkeypatch)

    response = client.post("/api/v1/auth/sign-out", headers=session_cookie_header(VALID_TOKEN))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_sign_out_wrong_csrf_header_returns_403(client, monkeypatch, session_cookie_header):
    _stub_valid_session(monkeypatch)

    response = client.post(
        "/api/v1/auth/sign-out",
        headers={**session_cookie_header(VALID_TOKEN), "X-CSRF-Token": "not-the-right-token"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_sign_out_rejected_by_csrf_leaves_the_session_usable_afterwards(
    client, monkeypatch, session_cookie_header
):
    _stub_valid_session(monkeypatch)

    rejected = client.post("/api/v1/auth/sign-out", headers=session_cookie_header(VALID_TOKEN))
    assert rejected.status_code == 403

    still_valid = client.get("/api/v1/users/me", headers=session_cookie_header(VALID_TOKEN))
    assert still_valid.status_code == 200


def test_sign_out_without_cookie_returns_401_before_csrf_is_ever_checked(client, monkeypatch):
    resolve_calls = []

    async def fake_resolve_session(db, *, token):
        resolve_calls.append(token)
        return make_session(user_id=USER_ID, csrf_token=CSRF_TOKEN)

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)

    # No X-CSRF-Token header either - if CSRF were checked first this would
    # also fail, so the missing cookie is what must be reported.
    response = client.post("/api/v1/auth/sign-out")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert resolve_calls == []
