"""Behavioural tests for `/auth/*`: registration, login, logout, `/me`.

Uses the in-memory `FakeAsyncSession` from `tests/services/conftest.py` behind
`get_db_session`, so the real service layer (`user_service`, `session_service`)
runs end to end through the endpoints — registration really creates a row,
login really authenticates against it, and the session/CSRF cookies really
round-trip through the `TestClient`'s cookie jar. Nothing here opens a real
database connection or event loop of its own (see `docs/qa-checklist.md`).
"""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx2 import Headers

from app.api.deps import current_admin
from app.db.models.user import User, UserRole
from app.db.session import get_db_session
from tests.services.conftest import FakeAsyncSession


def _cookie(headers: Headers, name: str) -> str | None:
    """Return the full `Set-Cookie` line for `name`, or `None`."""
    for line in headers.get_list("set-cookie"):
        if line.startswith(f"{name}="):
            return line
    return None


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def auth_client(api: FastAPI, fake_session: FakeAsyncSession) -> Iterator[TestClient]:
    """A `TestClient` whose `get_db_session` is the in-memory fake store."""
    api.dependency_overrides[get_db_session] = lambda: fake_session
    with TestClient(api) as test_client:
        yield test_client
    api.dependency_overrides.clear()


def _register(client: TestClient, username: str, password: str = "secret123") -> dict:
    response = client.post("/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def _login(
    client: TestClient, username: str, password: str = "secret123", remember_me: bool = False
):
    return client.post(
        "/auth/login",
        json={"username": username, "password": password, "rememberMe": remember_me},
    )


# --- POST /auth/register ----------------------------------------------------


def test_register_returns_201_with_camelcase_body_and_no_cookies(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/register", json={"username": "Alice", "password": "secret123"}
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"id", "username", "role"}
    assert body["username"] == "alice"
    assert body["role"] == "user"
    assert len(body["id"]) == 26
    assert response.headers.get_list("set-cookie") == []


def test_register_username_is_stripped_and_lowercased(auth_client: TestClient) -> None:
    body = _register(auth_client, "  Carol_01  ")

    assert body["username"] == "carol_01"


def test_register_duplicate_username_returns_409(auth_client: TestClient) -> None:
    _register(auth_client, "bob")

    response = auth_client.post("/auth/register", json={"username": "BOB", "password": "secret123"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Username is already taken."}


def test_register_short_password_returns_422_with_field_location(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/auth/register", json={"username": "validname", "password": "short12"}
    )

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "password") in locs


def test_register_invalid_username_returns_422_with_field_location(
    auth_client: TestClient,
) -> None:
    response = auth_client.post("/auth/register", json={"username": "ab", "password": "secret123"})

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "username") in locs


def test_register_username_with_disallowed_characters_returns_422(
    auth_client: TestClient,
) -> None:
    response = auth_client.post(
        "/auth/register", json={"username": "bad user!", "password": "secret123"}
    )

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "username") in locs


# --- POST /auth/login --------------------------------------------------------


def test_login_success_sets_pinned_cookie_attributes_without_remember_me(
    auth_client: TestClient,
) -> None:
    _register(auth_client, "dana")

    response = _login(auth_client, "dana")

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "dana"
    assert body["role"] == "user"

    session_cookie = _cookie(response.headers, "session")
    csrf_cookie = _cookie(response.headers, "csrf_token")
    assert session_cookie is not None
    assert csrf_cookie is not None

    assert "HttpOnly" in session_cookie
    assert "SameSite=Lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Secure" not in session_cookie
    assert "Max-Age" not in session_cookie

    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=Lax" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "Secure" not in csrf_cookie
    assert "Max-Age" not in csrf_cookie


def test_login_with_remember_me_sets_max_age_2592000_on_both_cookies(
    auth_client: TestClient,
) -> None:
    _register(auth_client, "erin")

    response = _login(auth_client, "erin", remember_me=True)

    session_cookie = _cookie(response.headers, "session")
    csrf_cookie = _cookie(response.headers, "csrf_token")
    assert session_cookie is not None
    assert csrf_cookie is not None
    assert "Max-Age=2592000" in session_cookie
    assert "Max-Age=2592000" in csrf_cookie


def test_login_wrong_password_returns_401_and_sets_no_cookies(auth_client: TestClient) -> None:
    _register(auth_client, "frank")

    response = _login(auth_client, "frank", password="wrongpassword")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}
    assert response.headers.get_list("set-cookie") == []


def test_login_unknown_username_returns_401(auth_client: TestClient) -> None:
    response = _login(auth_client, "ghost", password="whatever1")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}


# Login applies no format validation (unlike register): a credential that is
# too short to be valid is a wrong credential, so it must fail with 401 and
# not with a 422 the SPA would show as a generic server error.


def test_login_with_too_short_password_returns_401_not_422(auth_client: TestClient) -> None:
    _register(auth_client, "liam")

    response = _login(auth_client, "liam", password="short12")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}


@pytest.mark.parametrize("username", ["ab", "bad user!"])
def test_login_with_invalid_username_returns_401_not_422(
    auth_client: TestClient, username: str
) -> None:
    response = _login(auth_client, username, password="secret123")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}


# The one sanctioned exception (OQ-A): `password` still gets no format rule,
# but a length ceiling caps the Argon2 work a single attempt can demand.


def test_login_with_a_1024_char_password_returns_401_not_422(auth_client: TestClient) -> None:
    """At the ceiling, the request still reaches the credential check."""
    response = _login(auth_client, "nobody", password="x" * 1024)

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid username or password."}


def test_login_with_a_1025_char_password_returns_422(auth_client: TestClient) -> None:
    response = _login(auth_client, "nobody", password="x" * 1025)

    assert response.status_code == 422
    locs = [tuple(error["loc"]) for error in response.json()["detail"]]
    assert ("body", "password") in locs


# --- GET /auth/me -------------------------------------------------------------


def test_me_returns_current_user_with_valid_session(auth_client: TestClient) -> None:
    _register(auth_client, "gail")
    _login(auth_client, "gail")

    response = auth_client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == "gail"


def test_me_without_session_cookie_returns_401(auth_client: TestClient) -> None:
    response = auth_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_me_with_invalid_session_cookie_returns_401(auth_client: TestClient) -> None:
    auth_client.cookies.set("session", "not-a-real-token")

    response = auth_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_me_reflects_role_fresh_from_the_database(
    auth_client: TestClient, fake_session: FakeAsyncSession
) -> None:
    registered = _register(auth_client, "hank")
    _login(auth_client, "hank")

    # Simulate an out-of-band role change (e.g. the admin CLI), bypassing the
    # object the session was created against.
    fake_session.users[registered["id"]].role = UserRole.ADMIN

    response = auth_client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


# --- POST /auth/logout ---------------------------------------------------------


def test_logout_without_csrf_header_returns_403(auth_client: TestClient) -> None:
    _register(auth_client, "ivan")
    _login(auth_client, "ivan")

    response = auth_client.post("/auth/logout")

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid."}


def test_logout_with_mismatched_csrf_header_returns_403(auth_client: TestClient) -> None:
    _register(auth_client, "jane")
    _login(auth_client, "jane")

    response = auth_client.post("/auth/logout", headers={"X-CSRF-Token": "wrong-value"})

    assert response.status_code == 403
    assert response.json() == {"detail": "CSRF token missing or invalid."}


def test_logout_without_session_returns_401_even_with_a_csrf_header(
    auth_client: TestClient,
) -> None:
    response = auth_client.post("/auth/logout", headers={"X-CSRF-Token": "irrelevant"})

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated."}


def test_logout_success_clears_both_cookies_and_revokes_the_session(
    auth_client: TestClient,
) -> None:
    _register(auth_client, "kim")
    _login(auth_client, "kim")
    csrf_token = auth_client.cookies["csrf_token"]

    response = auth_client.post("/auth/logout", headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 204
    assert response.content == b""

    session_cookie = _cookie(response.headers, "session")
    csrf_cookie = _cookie(response.headers, "csrf_token")
    assert session_cookie is not None
    assert csrf_cookie is not None

    assert "Max-Age=0" in session_cookie
    assert "Path=/" in session_cookie
    assert "SameSite=Lax" in session_cookie
    assert "HttpOnly" in session_cookie

    assert "Max-Age=0" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "SameSite=Lax" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie

    # The session row is gone: a fresh /me with the (now-cleared) jar fails.
    me_response = auth_client.get("/auth/me")
    assert me_response.status_code == 401


# --- current_admin -------------------------------------------------------------
# No admin-only route exists yet (Phase 2), so the dependency is exercised
# directly rather than through a mounted endpoint.


def test_current_admin_rejects_non_admin_role() -> None:
    user = User(id="0" * 26, username="regular", password_hash="x", role=UserRole.USER)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(current_admin(user))

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == "Admin privileges required."


def test_current_admin_allows_admin_role() -> None:
    admin = User(id="1" * 26, username="root", password_hash="x", role=UserRole.ADMIN)

    result = asyncio.run(current_admin(admin))

    assert result is admin
