"""The turn route over the wire (sprint 03, WI2, I1): request/response
shape, validation and every error-code mapping. `game.service.run_turn`
is monkeypatched directly per the interface fixed in the sprint's
plan.md -- sibling WI1 owns that function's implementation (it may not
exist yet when this file runs, since WI1 and WI2 run in parallel:
`raising=False` on every `monkeypatch.setattr` below lets this suite
stand entirely on the I1/I2 contract, same pattern as
`tests/core/llm/test_commands_image.py`). AC1-AC6 (which kind gets
picked, from what state) belong to qa's black-box acceptance suite, not
here -- this file only proves the wire: shape, validation, and that every
`PlaythroughError`/`GameError` subclass reaches the caller as the one
envelope with its own code."""

from types import SimpleNamespace

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.game import service as game_service
from app.modules.game.errors import GameError
from app.modules.playthrough.errors import (
    CampaignRunNotFoundError,
    InvalidRunStatusError,
    RunArchivedError,
)
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

USER_ID = generate_id()
RUN_ID = generate_id()
CSRF_TOKEN = "the-matching-csrf-token"  # noqa: S105 - fixture value, not a secret


def _stub_auth(monkeypatch, *, user_id: str = USER_ID, csrf_token: str = CSRF_TOKEN):
    session = make_session(user_id=user_id, csrf_token=csrf_token)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


def _auth_headers(session_cookie_header):
    return {**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN}


def _make_outcome(**overrides):
    fields = dict(turn_id=generate_id(), kind="action", awaiting="none")
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _game_error(code, *, details=None):
    error = GameError()
    error.code = code
    if details is not None:
        error.details = details
    return error


def _stub_run_turn(monkeypatch, fn):
    monkeypatch.setattr(game_service, "run_turn", fn, raising=False)


def test_run_turn_response_has_exactly_the_camelcase_field_set(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    outcome = _make_outcome(turn_id="a-turn-id", kind="roll", awaiting="roll:a-roll-id")

    async def fake_run_turn(db, *, user_id, run_id, text):
        return outcome

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "I open the door"},
        headers=_auth_headers(session_cookie_header),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {"turnId": "a-turn-id", "kind": "roll", "awaiting": "roll:a-roll-id"}


def test_run_turn_passes_the_run_id_and_text_through_untouched(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_run_turn(db, *, user_id, run_id, text):
        calls.append((user_id, run_id, text))
        return _make_outcome()

    _stub_run_turn(monkeypatch, fake_run_turn)

    client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "I search the room"},
        headers=_auth_headers(session_cookie_header),
    )

    assert calls == [(USER_ID, RUN_ID, "I search the room")]


def test_run_turn_with_null_text_is_accepted_and_passed_through_as_none(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_run_turn(db, *, user_id, run_id, text):
        calls.append(text)
        return _make_outcome(kind="opening")

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": None},
        headers=_auth_headers(session_cookie_header),
    )

    assert response.status_code == 200, response.text
    assert calls == [None]


def test_run_turn_rejects_a_body_naming_anything_beyond_text(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_run_turn(db, *, user_id, run_id, text):
        calls.append(text)
        return _make_outcome()

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "roll for it", "kind": "roll"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=422, code="VALIDATION_ERROR")
    assert calls == []


def test_run_turn_rejects_text_over_2000_characters(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_run_turn(db, *, user_id, run_id, text):
        return _make_outcome()

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "x" * 2001},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=422, code="VALIDATION_ERROR")


def test_run_turn_without_session_cookie_returns_401_and_never_calls_service(
    client, monkeypatch
):
    calls = []

    async def fake_run_turn(db, *, user_id, run_id, text):
        calls.append(text)
        return _make_outcome()

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(f"/api/v1/game/runs/{RUN_ID}/turn", json={"text": "hello"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert calls == []


def test_run_turn_without_csrf_header_returns_403_and_never_calls_service(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_run_turn(db, *, user_id, run_id, text):
        calls.append(text)
        return _make_outcome()

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "hello"},
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    assert calls == []


def test_run_turn_translates_campaign_run_not_found_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_run_turn(db, *, user_id, run_id, text):
        raise CampaignRunNotFoundError(run_id)

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "hello"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=404, code="NOT_FOUND")


def test_run_turn_translates_run_archived_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_run_turn(db, *, user_id, run_id, text):
        raise RunArchivedError(run_id)

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "hello"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=409, code="RUN_ARCHIVED")


def test_run_turn_translates_invalid_run_status_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_run_turn(db, *, user_id, run_id, text):
        raise InvalidRunStatusError(run_id)

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "hello"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=409, code="INVALID_RUN_STATUS")


def test_run_turn_translates_action_not_available_game_error_with_details(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)
    details = {"awaiting": "answer:a-question-id", "options": ["fight", "flee"]}

    async def fake_run_turn(db, *, user_id, run_id, text):
        raise _game_error(ErrorCode.ACTION_NOT_AVAILABLE, details=details)

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "an answer nobody offered"},
        headers=_auth_headers(session_cookie_header),
    )

    error = assert_error_envelope(response, status=409, code="ACTION_NOT_AVAILABLE")
    assert error["details"] == details


def test_run_turn_translates_an_llm_game_error_to_502(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_run_turn(db, *, user_id, run_id, text):
        raise _game_error(ErrorCode.LLM_TIMEOUT)

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "hello"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=502, code="LLM_TIMEOUT")


def test_run_turn_translates_an_internal_game_error_to_500(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_run_turn(db, *, user_id, run_id, text):
        raise _game_error(ErrorCode.INTERNAL_ERROR)

    _stub_run_turn(monkeypatch, fake_run_turn)

    response = client.post(
        f"/api/v1/game/runs/{RUN_ID}/turn",
        json={"text": "hello"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=500, code="INTERNAL_ERROR")
