"""§8 criteria 18-20: POST /api/v1/auth/sign-in.

Also covers the unnumbered D25/D37 failed-sign-in log event (no §8 criterion
names it directly)."""

from app.modules.auth import service as auth_service
from app.modules.auth.service import IssuedSession
from app.modules.users import service as users_service
from tests.conftest import SESSION_TTL_SECONDS
from tests.factories import make_user


def test_sign_in_returns_200_with_user_body_cookie_and_csrf_header(client, monkeypatch):
    user = make_user(username="aragorn")

    async def fake_verify_credentials(db, *, username, password):
        return user

    async def fake_create_session(db, *, user):
        return IssuedSession(
            token="sign-in-token", csrf_token="sign-in-csrf", max_age=SESSION_TTL_SECONDS
        )

    monkeypatch.setattr(users_service, "verify_credentials", fake_verify_credentials)
    monkeypatch.setattr(auth_service, "create_session", fake_create_session)

    response = client.post(
        "/api/v1/auth/sign-in", json={"username": "aragorn", "password": "hunter-of-orcs"}
    )

    assert response.status_code == 200
    assert response.json()["username"] == "aragorn"
    assert response.cookies["session"] == "sign-in-token"
    assert response.headers["x-csrf-token"] == "sign-in-csrf"


def test_sign_in_always_issues_a_fresh_session_cookie(client, monkeypatch):
    """Two sign-ins - modelling "register, then sign in again" - must not
    share a cookie value: sign-in always creates a *new* session row and
    ignores any existing one (§5.4)."""
    user = make_user(username="aragorn")
    issued = iter(
        [
            IssuedSession(token="token-one", csrf_token="csrf-one", max_age=SESSION_TTL_SECONDS),
            IssuedSession(token="token-two", csrf_token="csrf-two", max_age=SESSION_TTL_SECONDS),
        ]
    )

    async def fake_verify_credentials(db, *, username, password):
        return user

    async def fake_create_session(db, *, user):
        return next(issued)

    monkeypatch.setattr(users_service, "verify_credentials", fake_verify_credentials)
    monkeypatch.setattr(auth_service, "create_session", fake_create_session)

    payload = {"username": "aragorn", "password": "hunter-of-orcs"}
    first = client.post("/api/v1/auth/sign-in", json=payload)
    second = client.post("/api/v1/auth/sign-in", json=payload)

    assert first.cookies["session"] != second.cookies["session"]


def test_sign_in_unknown_username_and_wrong_password_yield_the_identical_response(
    client, monkeypatch, assert_error_envelope
):
    async def fake_verify_credentials(db, *, username, password):
        return None

    monkeypatch.setattr(users_service, "verify_credentials", fake_verify_credentials)

    unknown_user = client.post(
        "/api/v1/auth/sign-in", json={"username": "nobody-registered", "password": "whatever1"}
    )
    wrong_password = client.post(
        "/api/v1/auth/sign-in", json={"username": "aragorn", "password": "wrong-password"}
    )

    error_a = assert_error_envelope(unknown_user, status=401, code="INVALID_CREDENTIALS")
    error_b = assert_error_envelope(wrong_password, status=401, code="INVALID_CREDENTIALS")
    assert error_a == error_b  # one code, one message, no enumeration signal


def test_sign_in_failure_logs_the_submitted_username_at_info_on_both_branches(
    client, monkeypatch, capsys
):
    """§6.1, `shared-knowledge.md` D25/D37: a failed sign-in logs the
    *submitted* username at INFO under the event name `sign_in_failed` - and
    only the username, never the password - on both the unknown-username and
    the wrong-password branch. `verify_credentials` collapses both to `None`
    (one code path), but the two remain indistinguishable to the caller
    (§5.4, criterion 19) and must stay distinguishable to an operator reading
    the log, which is the whole point of D25 - so both branches are asserted
    here, not just one.

    `capsys`, not `caplog`, for the same reason as criterion 28's test:
    structlog writes straight to `sys.stderr` and bypasses stdlib `logging`,
    and `capsys` only captures what is written *after* pytest replaces
    `sys.stderr`, so `configure_logging()` must run inside this test body."""
    from app.core.logging import configure_logging

    configure_logging()

    async def fake_verify_credentials(db, *, username, password):
        return None

    monkeypatch.setattr(users_service, "verify_credentials", fake_verify_credentials)

    unknown_password = "does-not-matter-1"
    wrong_password = "definitely-wrong-2"

    unknown_response = client.post(
        "/api/v1/auth/sign-in",
        json={"username": "nobody-registered", "password": unknown_password},
    )
    unknown_captured = capsys.readouterr()

    wrong_response = client.post(
        "/api/v1/auth/sign-in",
        json={"username": "aragorn", "password": wrong_password},
    )
    wrong_captured = capsys.readouterr()

    assert unknown_response.status_code == 401
    assert wrong_response.status_code == 401

    assert "sign_in_failed" in unknown_captured.err
    assert "info" in unknown_captured.err.lower()
    assert "nobody-registered" in unknown_captured.err
    assert unknown_password not in unknown_captured.err

    assert "sign_in_failed" in wrong_captured.err
    assert "info" in wrong_captured.err.lower()
    assert "aragorn" in wrong_captured.err
    assert wrong_password not in wrong_captured.err


def test_sign_in_schema_has_no_username_pattern_so_it_401s_rather_than_422s(
    client, monkeypatch, assert_error_envelope
):
    # A value the register schema's pattern would reject (a space) must
    # still reach the service layer here and come back 401, never 422 - a
    # 422 would tell the caller the username could not possibly exist.
    async def fake_verify_credentials(db, *, username, password):
        return None

    monkeypatch.setattr(users_service, "verify_credentials", fake_verify_credentials)

    response = client.post("/api/v1/auth/sign-in", json={"username": "ara gorn", "password": "x"})

    assert response.status_code != 422
    assert_error_envelope(response, status=401, code="INVALID_CREDENTIALS")
