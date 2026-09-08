"""§8 criteria 26-28: the error envelope shape, the 404/405 catch-alls, and
the 500 catch-all with its log side effect.

Criterion 26 ("every non-2xx response in criteria 14-25 has this exact body
shape") is not proved by a single test here: it is proved collectively, by
every error-path test in this suite (auth/, users/, core/) going through the
shared `assert_error_envelope` fixture (`conftest.py`), which fails on any
extra or missing top-level key.
"""


def test_unknown_route_returns_404_not_found(client, assert_error_envelope):
    response = client.get("/api/v1/does-not-exist")
    assert_error_envelope(response, status=404, code="NOT_FOUND")


def test_known_path_wrong_method_returns_405_method_not_allowed(client, assert_error_envelope):
    # /api/v1/auth/sign-in only accepts POST.
    response = client.get("/api/v1/auth/sign-in")
    assert_error_envelope(response, status=405, code="METHOD_NOT_ALLOWED")


def test_unhandled_exception_returns_500_and_logs_the_traceback_to_stderr(
    error_client, monkeypatch, capsys, assert_error_envelope, session_cookie_header
):
    # capsys only captures what is written *after* pytest replaces
    # sys.stderr, so configure_logging() must run inside the test, not only
    # once at app-construction time (§6.1, §6.5).
    from app.core.logging import configure_logging
    from app.modules.auth import service as auth_service
    from app.modules.users import service as users_service
    from tests.factories import make_session, make_user

    configure_logging()
    user = make_user()

    async def fake_resolve_session(db, *, token):
        return make_session(user_id=user.id)

    async def fake_get_user_by_id(db, *, user_id):
        raise RuntimeError("deliberately raised to exercise the 500 path")

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)

    response = error_client.get(
        "/api/v1/users/me", headers=session_cookie_header("irrelevant-cookie-value")
    )

    error = assert_error_envelope(response, status=500, code="INTERNAL_ERROR")
    assert error["message"] == "An unexpected error occurred."
    assert "RuntimeError" not in response.text
    assert "Traceback" not in response.text
    assert "deliberately raised" not in response.text

    captured = capsys.readouterr()
    assert "Traceback" in captured.err
    assert "deliberately raised to exercise the 500 path" in captured.err
