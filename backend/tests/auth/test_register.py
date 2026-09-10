"""§8 criteria 12-15: POST /api/v1/auth/register.

Criteria 16-17 (the stored Argon2 hash, the stored token-hash format, "the
cookie value does not appear in the `sessions` table") are DB-observation
criteria this engine-free suite cannot reach directly - see the QA report.
This file covers the wire contract and delegates the Argon2/token-shape
assertions to `tests/core/test_security.py`, which tests the underlying
primitives directly.
"""

import re
from datetime import datetime

import pytest

from app.core.errors import ApiError, ErrorCode
from app.modules.auth import service as auth_service
from app.modules.auth.service import IssuedSession
from app.modules.users import service as users_service
from tests.conftest import SESSION_TTL_SECONDS
from tests.factories import make_user

ULID_PATTERN = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")

VALID_PAYLOAD = {"username": "Aragorn", "password": "hunter-of-orcs"}


def _stub_successful_register(
    monkeypatch, *, username="aragorn", token="issued-token", csrf_token="issued-csrf"
):
    user = make_user(username=username)

    async def fake_create_user(db, *, username, password):
        return user

    async def fake_create_session(db, *, user):
        return IssuedSession(token=token, csrf_token=csrf_token, max_age=SESSION_TTL_SECONDS)

    monkeypatch.setattr(users_service, "create_user", fake_create_user)
    monkeypatch.setattr(auth_service, "create_session", fake_create_session)
    return user


def test_register_returns_201_with_lowercased_username_id_createdat_cookie_and_csrf_header(
    client, monkeypatch
):
    user = _stub_successful_register(monkeypatch)

    response = client.post("/api/v1/auth/register", json=VALID_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "aragorn"  # the stored, lower-cased form (§5.3)
    assert body["id"] == str(user.id)
    assert isinstance(body["id"], str)
    assert ULID_PATTERN.fullmatch(body["id"])  # D38: emitted id is a ULID string, not a UUID
    datetime.fromisoformat(body["createdAt"])  # parses; literal spelling is not asserted (§5.3)

    assert "session" in response.cookies
    assert response.headers["x-csrf-token"] == "issued-csrf"


def test_register_session_cookie_attributes_in_development(client, monkeypatch):
    _stub_successful_register(monkeypatch, token="a-session-token-value")

    response = client.post("/api/v1/auth/register", json=VALID_PAYLOAD)

    set_cookie = response.headers["set-cookie"]
    assert "a-session-token-value" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/" in set_cookie
    assert "samesite=lax" in set_cookie.lower()
    assert f"Max-Age={SESSION_TTL_SECONDS}" in set_cookie
    assert "secure" not in set_cookie.lower()


def test_register_session_cookie_has_secure_flag_in_production(production_client, monkeypatch):
    _stub_successful_register(monkeypatch, token="a-prod-session-token")

    response = production_client.post("/api/v1/auth/register", json=VALID_PAYLOAD)

    assert "secure" in response.headers["set-cookie"].lower()


@pytest.mark.parametrize(
    "payload", [VALID_PAYLOAD, {"username": "ARAGORN", "password": "hunter-of-orcs"}]
)
def test_register_duplicate_username_returns_409_username_taken(client, monkeypatch, payload):
    async def fake_create_user(db, *, username, password):
        raise ApiError(ErrorCode.USERNAME_TAKEN)

    monkeypatch.setattr(users_service, "create_user", fake_create_user)

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "USERNAME_TAKEN"


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ab", "password": "hunter-of-orcs"},  # too short (min 3)
        {"username": "ara gorn", "password": "hunter-of-orcs"},  # violates the pattern
        {"username": "aragorn", "password": "short"},  # too short (min 8)
    ],
)
def test_register_validation_error_returns_422_with_details_fields(
    client, payload, assert_error_envelope
):
    response = client.post("/api/v1/auth/register", json=payload)

    error = assert_error_envelope(response, status=422, code="VALIDATION_ERROR")
    assert isinstance(error["details"]["fields"], list)
    assert len(error["details"]["fields"]) >= 1
