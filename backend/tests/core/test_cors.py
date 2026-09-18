"""§8 criteria 29-30: CORS, split deliberately along Starlette's own split
between preflight and simple responses (§5.9).

Criterion 29 is the preflight set and must NOT assert
`access-control-expose-headers` - Starlette's `CORSMiddleware` only puts that
header on simple responses, so asserting it here would fail a byte-correct
build. Criterion 30 is the simple-response set, asserted on the sign-in `200`.
"""

from app.modules.auth import service as auth_service
from app.modules.auth.service import IssuedSession
from app.modules.users import service as users_service
from tests.conftest import FRONTEND_ORIGIN, SESSION_TTL_SECONDS
from tests.factories import make_user


def test_preflight_for_sign_in_has_the_preflight_cors_set(client):
    response = client.options(
        "/api/v1/auth/sign-in",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type, x-csrf-token",
        },
    )

    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    allow_headers = response.headers["access-control-allow-headers"].lower()
    assert "x-csrf-token" in allow_headers
    # Deliberately not asserted here - see the module docstring.
    assert "access-control-expose-headers" not in response.headers


def test_preflight_for_renaming_a_campaign_run_has_the_preflight_cors_set(client):
    # `PATCH` is only used by the playthrough rename endpoint (005/04) --
    # without it in `allow_methods`, this preflight would fail in a
    # browser even though every same-origin test client call still passes.
    response = client.options(
        "/api/v1/playthrough/campaign/some-run-id",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "content-type, x-csrf-token",
        },
    )

    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    allow_methods = response.headers["access-control-allow-methods"]
    assert "PATCH" in allow_methods
    allow_headers = response.headers["access-control-allow-headers"].lower()
    assert "x-csrf-token" in allow_headers
    # Deliberately not asserted here - see the module docstring.
    assert "access-control-expose-headers" not in response.headers


def test_sign_in_success_response_has_the_simple_response_cors_set(client, monkeypatch):
    user = make_user(username="aragorn")

    async def fake_verify_credentials(db, *, username, password):
        return user

    async def fake_create_session(db, *, user):
        return IssuedSession(
            token="cors-token", csrf_token="cors-csrf", max_age=SESSION_TTL_SECONDS
        )

    monkeypatch.setattr(users_service, "verify_credentials", fake_verify_credentials)
    monkeypatch.setattr(auth_service, "create_session", fake_create_session)

    response = client.post(
        "/api/v1/auth/sign-in",
        json={"username": "aragorn", "password": "hunter-of-orcs"},
        headers={"Origin": FRONTEND_ORIGIN},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
    expose_headers = response.headers["access-control-expose-headers"].lower()
    assert "x-csrf-token" in expose_headers
