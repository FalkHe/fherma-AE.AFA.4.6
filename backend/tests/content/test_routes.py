"""Tests for `GET /api/v1/content/campaigns` (WI1).

Behaviours: 200 list at each campaign's newest valid version, anonymous 401,
an invalid newest version skips that campaign (others still list), and a
campaign directory with no version subdirectories is skipped too.
"""

from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.users import service as users_service
from tests.content.conftest import build_version_dir, campaign
from tests.factories import make_session, make_user

USER_ID = generate_id()


def _sign_in(monkeypatch):
    session = make_session(user_id=USER_ID)
    user = make_user(user_id=USER_ID)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


def test_lists_each_campaign_at_its_newest_valid_version(
    client, monkeypatch, session_cookie_header, content_root
):
    _sign_in(monkeypatch)
    build_version_dir(
        content_root,
        "greenhollow",
        "v1",
        campaign=campaign(id="greenhollow", title="Greenhollow", summary="The first telling."),
    )
    build_version_dir(
        content_root,
        "greenhollow",
        "v2",
        campaign=campaign(
            id="greenhollow", title="Greenhollow Reforged", summary="The second telling."
        ),
    )
    build_version_dir(content_root, "hollow-reach", "v1")

    response = client.get(
        "/api/v1/content/campaigns", headers=session_cookie_header("a-valid-cookie")
    )

    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body} == {"greenhollow", "hollow-reach"}
    greenhollow = next(item for item in body if item["id"] == "greenhollow")
    assert greenhollow["title"] == "Greenhollow Reforged"
    assert greenhollow["summary"] == "The second telling."
    assert greenhollow["adventureCount"] == 1
    assert set(greenhollow.keys()) == {"id", "title", "summary", "adventureCount"}


def test_anonymous_request_returns_401_not_authenticated(client, assert_error_envelope):
    response = client.get("/api/v1/content/campaigns")

    error = assert_error_envelope(response, status=401, code="NOT_AUTHENTICATED")
    assert error["message"] == "Authentication required."


def test_campaign_with_invalid_newest_version_is_skipped(
    client, monkeypatch, session_cookie_header, content_root
):
    _sign_in(monkeypatch)
    build_version_dir(content_root, "hollow-reach", "v1")
    build_version_dir(content_root, "broken-campaign", "v1", campaign=None)

    response = client.get(
        "/api/v1/content/campaigns", headers=session_cookie_header("a-valid-cookie")
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {"hollow-reach"}


def test_campaign_directory_with_no_versions_is_skipped(
    client, monkeypatch, session_cookie_header, content_root
):
    _sign_in(monkeypatch)
    build_version_dir(content_root, "hollow-reach", "v1")
    (content_root / "campaigns" / "empty-campaign").mkdir(parents=True)

    response = client.get(
        "/api/v1/content/campaigns", headers=session_cookie_header("a-valid-cookie")
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {"hollow-reach"}
