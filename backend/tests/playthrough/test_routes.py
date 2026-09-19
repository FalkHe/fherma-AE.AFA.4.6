"""Wiring the acceptance tests do not cover (I1-I4): authentication is
required on all three routes, CSRF is required on the POST, the response
carries exactly the camelCase field set of `CampaignRunRead`, every
`PlaythroughError` subclass reaches the wire as the one error envelope via
`except PlaythroughError as exc: raise ApiError(exc.code) from exc`, and a
foreign run and an unknown run are indistinguishable on the wire.

Stubbed session (`app.core.db.get_db_session` override, see
`tests/conftest.py`), `app.modules.playthrough.service` monkeypatched --
never imported by name (AGENTS.md) -- exactly as `tests/users/test_routes.py`
does it for its own module.
"""

from datetime import UTC, datetime
from types import SimpleNamespace

from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import (
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
    CharacterExistsError,
    InvalidRunStatusError,
    RunArchivedError,
)
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

USER_ID = generate_id()
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


def _make_run(**overrides):
    fields = dict(
        id=generate_id(),
        campaign_id="greenhollow",
        content_version="v1",
        title=None,
        status="setup",
        created_at=datetime.now(UTC),
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _auth_headers(session_cookie_header):
    return {**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN}


def _make_character(**overrides):
    fields = dict(
        id=generate_id(),
        name="Rosalind Thorn",
        current_hp=12,
        max_hp=12,
        armour_class=15,
        member_id=generate_id(),
        template_id=None,
        instance_key="pc:member-placeholder:1",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def test_start_campaign_run_response_has_exactly_the_camelcase_field_set(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    run = _make_run()

    async def fake_start(db, *, user_id, campaign_id):
        return run

    monkeypatch.setattr(playthrough_service, "start_campaign_run", fake_start)

    response = client.post(
        "/api/v1/playthrough/campaign",
        json={"campaignId": "greenhollow"},
        headers=_auth_headers(session_cookie_header),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "campaignId",
        "contentVersion",
        "title",
        "status",
        "createdAt",
    }


def test_start_campaign_run_without_session_cookie_returns_401(client, monkeypatch):
    calls = []

    async def fake_start(db, *, user_id, campaign_id):
        calls.append((user_id, campaign_id))
        return _make_run()

    monkeypatch.setattr(playthrough_service, "start_campaign_run", fake_start)

    response = client.post("/api/v1/playthrough/campaign", json={"campaignId": "greenhollow"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert calls == []


def test_start_campaign_run_without_csrf_header_returns_403_and_never_calls_service(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_start(db, *, user_id, campaign_id):
        calls.append((user_id, campaign_id))
        return _make_run()

    monkeypatch.setattr(playthrough_service, "start_campaign_run", fake_start)

    response = client.post(
        "/api/v1/playthrough/campaign",
        json={"campaignId": "greenhollow"},
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    assert calls == []


def test_start_campaign_run_translates_campaign_not_found_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_start(db, *, user_id, campaign_id):
        raise CampaignNotFoundError(campaign_id)

    monkeypatch.setattr(playthrough_service, "start_campaign_run", fake_start)

    response = client.post(
        "/api/v1/playthrough/campaign",
        json={"campaignId": "no-such-campaign"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=404, code="NOT_FOUND")


def test_start_campaign_run_translates_campaign_run_exists_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_start(db, *, user_id, campaign_id):
        raise CampaignRunExistsError(campaign_id)

    monkeypatch.setattr(playthrough_service, "start_campaign_run", fake_start)

    response = client.post(
        "/api/v1/playthrough/campaign",
        json={"campaignId": "greenhollow"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=409, code="ALREADY_STARTED")


def test_list_campaign_runs_response_items_have_exactly_the_camelcase_field_set(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    run = _make_run()

    async def fake_list(db, *, user_id):
        return [run]

    monkeypatch.setattr(playthrough_service, "list_campaign_runs", fake_list)

    response = client.get(
        "/api/v1/playthrough/campaign", headers=session_cookie_header("a-valid-cookie")
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert set(body[0].keys()) == {
        "id",
        "campaignId",
        "contentVersion",
        "title",
        "status",
        "createdAt",
    }


def test_list_campaign_runs_without_session_cookie_returns_401(client, monkeypatch):
    async def fake_list(db, *, user_id):
        return [_make_run()]

    monkeypatch.setattr(playthrough_service, "list_campaign_runs", fake_list)

    response = client.get("/api/v1/playthrough/campaign")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_get_campaign_run_without_session_cookie_returns_401(client, monkeypatch):
    async def fake_get(db, *, user_id, run_id):
        return _make_run()

    monkeypatch.setattr(playthrough_service, "get_campaign_run", fake_get)

    response = client.get("/api/v1/playthrough/campaign/some-run-id")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


def test_get_campaign_run_foreign_and_unknown_run_answer_the_identical_not_found_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # I4/D12: `_require_member` raises the same `CampaignRunNotFoundError`
    # whether the id is unknown outright or belongs to someone else --
    # nothing about the wire response may tell the two apart.
    _stub_auth(monkeypatch)

    async def fake_get_foreign(db, *, user_id, run_id):
        raise CampaignRunNotFoundError(run_id)

    monkeypatch.setattr(playthrough_service, "get_campaign_run", fake_get_foreign)

    foreign_response = client.get(
        "/api/v1/playthrough/campaign/someone-elses-run-id",
        headers=session_cookie_header("a-valid-cookie"),
    )
    unknown_response = client.get(
        "/api/v1/playthrough/campaign/no-such-run-id",
        headers=session_cookie_header("a-valid-cookie"),
    )

    foreign_error = assert_error_envelope(foreign_response, status=404, code="NOT_FOUND")
    unknown_error = assert_error_envelope(unknown_response, status=404, code="NOT_FOUND")
    assert foreign_error == unknown_error


def test_get_campaign_run_response_has_exactly_the_camelcase_field_set(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    run = _make_run()

    async def fake_get(db, *, user_id, run_id):
        return run

    monkeypatch.setattr(playthrough_service, "get_campaign_run", fake_get)

    response = client.get(
        f"/api/v1/playthrough/campaign/{run.id}",
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "campaignId",
        "contentVersion",
        "title",
        "status",
        "createdAt",
    }


def test_create_character_response_has_exactly_the_camelcase_field_set(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    character = _make_character()

    async def fake_create_character(db, *, user_id, run_id, sheet=None):
        return character

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    response = client.post(
        "/api/v1/playthrough/campaign/some-run-id/character",
        headers=_auth_headers(session_cookie_header),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body.keys()) == {"id", "name", "currentHp", "maxHp", "armourClass"}


def test_create_character_without_session_cookie_returns_401(client, monkeypatch):
    calls = []

    async def fake_create_character(db, *, user_id, run_id, sheet=None):
        calls.append((user_id, run_id))
        return _make_character()

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    response = client.post("/api/v1/playthrough/campaign/some-run-id/character")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert calls == []


def test_create_character_without_csrf_header_returns_403_and_never_calls_service(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_create_character(db, *, user_id, run_id, sheet=None):
        calls.append((user_id, run_id))
        return _make_character()

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    response = client.post(
        "/api/v1/playthrough/campaign/some-run-id/character",
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    assert calls == []


def test_create_character_translates_character_exists_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_create_character(db, *, user_id, run_id, sheet=None):
        raise CharacterExistsError(run_id)

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    response = client.post(
        "/api/v1/playthrough/campaign/some-run-id/character",
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=409, code="CHARACTER_EXISTS")


def test_create_character_translates_run_archived_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_create_character(db, *, user_id, run_id, sheet=None):
        raise RunArchivedError(run_id)

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    response = client.post(
        "/api/v1/playthrough/campaign/some-run-id/character",
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=409, code="RUN_ARCHIVED")


def test_rename_campaign_run_response_has_exactly_the_camelcase_field_set(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    run = _make_run(title="New Title")

    async def fake_rename(db, *, user_id, run_id, title):
        return run

    monkeypatch.setattr(playthrough_service, "rename_campaign_run", fake_rename)

    response = client.patch(
        f"/api/v1/playthrough/campaign/{run.id}",
        json={"title": "New Title"},
        headers=_auth_headers(session_cookie_header),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "campaignId",
        "contentVersion",
        "title",
        "status",
        "createdAt",
    }
    assert body["title"] == "New Title"


def test_rename_campaign_run_without_session_cookie_returns_401(client, monkeypatch):
    calls = []

    async def fake_rename(db, *, user_id, run_id, title):
        calls.append((user_id, run_id, title))
        return _make_run()

    monkeypatch.setattr(playthrough_service, "rename_campaign_run", fake_rename)

    response = client.patch("/api/v1/playthrough/campaign/some-run-id", json={"title": "New Title"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert calls == []


def test_rename_campaign_run_without_csrf_header_returns_403_and_never_calls_service(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_rename(db, *, user_id, run_id, title):
        calls.append((user_id, run_id, title))
        return _make_run()

    monkeypatch.setattr(playthrough_service, "rename_campaign_run", fake_rename)

    response = client.patch(
        "/api/v1/playthrough/campaign/some-run-id",
        json={"title": "New Title"},
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    assert calls == []


def test_rename_campaign_run_translates_run_archived_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)

    async def fake_rename(db, *, user_id, run_id, title):
        raise RunArchivedError(run_id)

    monkeypatch.setattr(playthrough_service, "rename_campaign_run", fake_rename)

    response = client.patch(
        "/api/v1/playthrough/campaign/some-run-id",
        json={"title": "New Title"},
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=409, code="RUN_ARCHIVED")


def test_archive_campaign_run_without_session_cookie_returns_401(client, monkeypatch):
    calls = []

    async def fake_archive(db, *, user_id, run_id):
        calls.append((user_id, run_id))
        return None

    monkeypatch.setattr(playthrough_service, "archive_campaign_run", fake_archive)

    response = client.post("/api/v1/playthrough/campaign/some-run-id/archive")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert calls == []


def test_archive_campaign_run_without_csrf_header_returns_403_and_never_calls_service(
    client, monkeypatch, session_cookie_header
):
    _stub_auth(monkeypatch)
    calls = []

    async def fake_archive(db, *, user_id, run_id):
        calls.append((user_id, run_id))
        return None

    monkeypatch.setattr(playthrough_service, "archive_campaign_run", fake_archive)

    response = client.post(
        "/api/v1/playthrough/campaign/some-run-id/archive",
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    assert calls == []


def test_archive_campaign_run_translates_invalid_run_status_error_to_envelope(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # Exercises the third new domain code's translation through the wire:
    # not a status `archive_campaign_run` reaches on its own (it never
    # raises this), but every `PlaythroughError` subclass must reach the
    # identical envelope through this route's `except PlaythroughError`
    # handler regardless of which one is raised (I5).
    _stub_auth(monkeypatch)

    async def fake_archive(db, *, user_id, run_id):
        raise InvalidRunStatusError(run_id)

    monkeypatch.setattr(playthrough_service, "archive_campaign_run", fake_archive)

    response = client.post(
        "/api/v1/playthrough/campaign/some-run-id/archive",
        headers=_auth_headers(session_cookie_header),
    )

    assert_error_envelope(response, status=409, code="INVALID_RUN_STATUS")


def test_archived_run_still_reads_but_refuses_rename_and_character_creation(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    _stub_auth(monkeypatch)
    archived_run = _make_run(status="archived")

    async def fake_get(db, *, user_id, run_id):
        return archived_run

    monkeypatch.setattr(playthrough_service, "get_campaign_run", fake_get)

    read_response = client.get(
        f"/api/v1/playthrough/campaign/{archived_run.id}",
        headers=session_cookie_header("a-valid-cookie"),
    )
    assert read_response.status_code == 200, read_response.text
    assert read_response.json()["status"] == "archived"

    async def fake_rename(db, *, user_id, run_id, title):
        raise RunArchivedError(run_id)

    monkeypatch.setattr(playthrough_service, "rename_campaign_run", fake_rename)

    rename_response = client.patch(
        f"/api/v1/playthrough/campaign/{archived_run.id}",
        json={"title": "New Title"},
        headers=_auth_headers(session_cookie_header),
    )
    assert_error_envelope(rename_response, status=409, code="RUN_ARCHIVED")

    async def fake_create_character(db, *, user_id, run_id, sheet=None):
        raise RunArchivedError(run_id)

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    character_response = client.post(
        f"/api/v1/playthrough/campaign/{archived_run.id}/character",
        headers=_auth_headers(session_cookie_header),
    )
    assert_error_envelope(character_response, status=409, code="RUN_ARCHIVED")
