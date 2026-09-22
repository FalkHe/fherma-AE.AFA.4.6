"""qa acceptance tests -- sprint 007/01 "campaign catalogue read"
(docs/intents/007-initial-frontend/sprints/01-campaign-catalogue-read/brief.md).

Black-box over `GET /api/v1/content/campaigns` only -- this file never reads
`app/modules/content/routes.py`, `schemas.py` or `service.py`. Content trees
are built with the shared `tests/content/conftest.py` fixtures
(`content_root`, `build_version_dir`); auth is stubbed the way
`tests/users/test_routes.py:17-38` does it.

Written against the sprint brief and interface contracts (plan.md I1-I5),
not against the implementation landing in parallel -- every test here is
expected to fail now (the route does not exist yet), and to pass once that
work lands.
"""

from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.users import service as users_service
from tests.content.conftest import (
    adventure,
    build_version_dir,
    campaign,
    scene_approach,
    scene_floor,
)
from tests.factories import make_session, make_user

USER_ID = generate_id()


def _sign_in(monkeypatch):
    """Stubs a signed-in caller, mirroring `test_read_current_user_returns_200...`."""
    session = make_session(user_id=USER_ID)
    user = make_user(user_id=USER_ID)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


def test_ac1_lists_each_campaign_at_its_newest_version(
    client, monkeypatch, session_cookie_header, content_root
):
    """← AC1: one entry per campaign under the content root, at its newest
    version, with exactly id/title/summary/adventureCount in camelCase."""
    _sign_in(monkeypatch)

    # A single-version campaign: default valid content (seed character,
    # object templates, one adventure) from `tests/content/conftest.py`,
    # only the id/title/summary/adventure-set varied.
    build_version_dir(
        content_root,
        campaign_id="riverwatch",
        version="v1",
        campaign=campaign(
            id="riverwatch",
            title="Riverwatch",
            summary="A quiet watch on a river that is no longer quiet.",
        ),
    )

    # A two-version campaign; v1 and v2 differ in title/summary/adventure
    # count. Both versions reuse the same valid scene/template content, only
    # varying which adventures are present.
    build_version_dir(
        content_root,
        campaign_id="greenhollow",
        version="v1",
        campaign=campaign(
            id="greenhollow",
            title="Greenhollow (old)",
            summary="An older, shorter teaser.",
        ),
    )
    build_version_dir(
        content_root,
        campaign_id="greenhollow",
        version="v2",
        campaign=campaign(
            id="greenhollow",
            title="Greenhollow",
            summary="The newest teaser for Greenhollow.",
            adventures=["the-sunken-mill", "the-second-mill"],
        ),
        adventures={
            "the-sunken-mill": adventure(),
            # Distinct scene ids from "the-sunken-mill" -- the same ids
            # reused across adventures confuse the reachability check.
            "the-second-mill": adventure(
                id="the-second-mill",
                title="The Second Mill",
                entry_scene="second-mill-approach",
                scenes=[
                    scene_approach(
                        id="second-mill-approach",
                        exits=[
                            {
                                "id": "into-the-mill",
                                "to": "second-mill-floor",
                                "description": "The mill door, barred from within.",
                                "condition": (
                                    "the bar has been broken, forced, or lifted from outside"
                                ),
                            }
                        ],
                    ),
                    scene_floor(id="second-mill-floor"),
                ],
            ),
        },
    )

    response = client.get(
        "/api/v1/content/campaigns", headers=session_cookie_header("a-valid-cookie")
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    by_id = {entry["id"]: entry for entry in body}
    assert set(by_id.keys()) == {"riverwatch", "greenhollow"}

    for entry in body:
        assert set(entry.keys()) == {"id", "title", "summary", "adventureCount"}

    greenhollow = by_id["greenhollow"]
    assert greenhollow["title"] == "Greenhollow"
    assert greenhollow["summary"] == "The newest teaser for Greenhollow."
    assert greenhollow["adventureCount"] == 2

    riverwatch = by_id["riverwatch"]
    assert riverwatch["title"] == "Riverwatch"
    assert riverwatch["summary"] == "A quiet watch on a river that is no longer quiet."
    assert riverwatch["adventureCount"] == 1


def test_ac2_anonymous_caller_is_refused_with_standard_error_envelope(
    client, content_root, assert_error_envelope
):
    """← AC2: no session cookie -> 401 NOT_AUTHENTICATED, standard envelope."""
    response = client.get("/api/v1/content/campaigns")

    error = assert_error_envelope(response, status=401, code="NOT_AUTHENTICATED")
    assert error["message"] == "Authentication required."
    assert error["details"] is None
