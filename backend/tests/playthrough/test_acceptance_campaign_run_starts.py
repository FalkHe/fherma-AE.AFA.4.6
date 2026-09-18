"""qa acceptance tests -- sprint 005/03 "a campaign run starts with its
world already in it"
(`docs/intents/005-game-state-services/sprints/03-campaign-run-starts-with-world/brief.md`).

AC1 and AC2 are black-box over the wire (`TestClient`, stubbed `db` session):
the pinned `app.modules.playthrough.service` functions are monkeypatched the
same way every other route-test file in this suite does it (see
`tests/auth/test_register.py`, `tests/users/test_routes.py`) -- this file
never imports `app.modules.playthrough.routes`, `.schemas` or `.errors`, and
a stubbed service raises `app.core.errors.ApiError` directly rather than a
playthrough-specific exception class, exactly as `test_register.py`'s
`USERNAME_TAKEN` case does.

AC3 carries `@pytest.mark.database`: it drives the real
`playthrough_service.start_campaign_run` against the shared scratch-database
fixture (`playthrough_db`, `tests/playthrough/conftest.py`) and reads the
result back with plain SQL over `objects` / `campaign_runs` / `events` --
never the ORM model classes, so this file stays independent of anything
`app.modules.playthrough.models` happens to expose. The expected set of
object keys is derived from the shipped `greenhollow/v1` content
(`app.modules.content.service.load_campaign`) following the `instance_key`
algorithm the sprint plan hands QA (I5), rather than pasted as a literal
list, so this test survives an authored content change.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): the one async call
in AC3 is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service,
routes or schemas themselves -- this suite is red until WI1 (service) and
WI2 (routes/schemas) land, and green once they do.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.errors import ApiError, ErrorCode
from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.content import service as content_service
from app.modules.playthrough import service as playthrough_service
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


def test_ac1_starting_a_campaign_run_returns_it_and_guards_membership_auth_and_csrf(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # <- AC1
    _stub_auth(monkeypatch)
    run = _make_run()

    async def fake_start(db, *, user_id, campaign_id):
        assert user_id == USER_ID
        assert campaign_id == "greenhollow"
        return run

    monkeypatch.setattr(playthrough_service, "start_campaign_run", fake_start)

    response = client.post(
        "/api/v1/playthrough/campaign",
        json={"campaignId": "greenhollow"},
        headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
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
    }, body
    assert body["id"] == str(run.id)
    assert body["campaignId"] == "greenhollow"
    assert body["contentVersion"] == "v1"
    assert body["title"] is None
    assert body["status"] == "setup"
    datetime.fromisoformat(body["createdAt"])  # parses; literal spelling is not asserted

    # An unknown campaign answers the envelope with a stable domain code.
    async def fake_start_unknown(db, *, user_id, campaign_id):
        raise ApiError(ErrorCode.NOT_FOUND)

    monkeypatch.setattr(playthrough_service, "start_campaign_run", fake_start_unknown)

    unknown_response = client.post(
        "/api/v1/playthrough/campaign",
        json={"campaignId": "no-such-campaign"},
        headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
    )
    assert_error_envelope(unknown_response, status=404, code="NOT_FOUND")

    # The call requires authentication.
    no_auth_response = client.post(
        "/api/v1/playthrough/campaign", json={"campaignId": "greenhollow"}
    )
    assert_error_envelope(no_auth_response, status=401, code="NOT_AUTHENTICATED")

    # The call requires the CSRF header.
    no_csrf_response = client.post(
        "/api/v1/playthrough/campaign",
        json={"campaignId": "greenhollow"},
        headers=session_cookie_header("a-valid-cookie"),
    )
    assert_error_envelope(no_csrf_response, status=403, code="CSRF_TOKEN_INVALID")


def test_ac2_listing_is_scoped_to_the_caller_and_a_foreign_or_unknown_run_is_alike_not_found(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # <- AC2
    _stub_auth(monkeypatch)

    newer_run = _make_run(status="setup")
    older_archived_run = _make_run(status="archived")

    async def fake_list(db, *, user_id):
        assert user_id == USER_ID
        # The service is the one contract responsible for "newest first";
        # the route must simply hand back what it is given, unfiltered and
        # unreordered, archived runs included.
        return [newer_run, older_archived_run]

    monkeypatch.setattr(playthrough_service, "list_campaign_runs", fake_list)

    list_response = client.get(
        "/api/v1/playthrough/campaign", headers=session_cookie_header("a-valid-cookie")
    )
    assert list_response.status_code == 200, list_response.text
    body = list_response.json()
    assert [run["id"] for run in body] == [str(newer_run.id), str(older_archived_run.id)]
    assert {run["status"] for run in body} == {"setup", "archived"}

    # A run that exists but belongs to someone else answers NOT_FOUND -- the
    # same code an unknown id answers, never a distinct "forbidden".
    async def fake_get_foreign_or_unknown(db, *, user_id, run_id):
        raise ApiError(ErrorCode.NOT_FOUND)

    monkeypatch.setattr(playthrough_service, "get_campaign_run", fake_get_foreign_or_unknown)

    foreign_response = client.get(
        "/api/v1/playthrough/campaign/someone-elses-run-id",
        headers=session_cookie_header("a-valid-cookie"),
    )
    assert_error_envelope(foreign_response, status=404, code="NOT_FOUND")

    unknown_response = client.get(
        "/api/v1/playthrough/campaign/no-such-run-id",
        headers=session_cookie_header("a-valid-cookie"),
    )
    assert_error_envelope(unknown_response, status=404, code="NOT_FOUND")


def _expected_instance_keys(loaded_campaign) -> set[str]:
    """Every `instance_key` the content implies, by the sprint plan's
    algorithm (I5): `<adventure>:<scene>:<template>:<ordinal>` per placement
    instance, plus `<owner_key>/<template>:<ordinal>` per carried item on
    that instance. Derived from the shipped JSON rather than pasted, so an
    authored content change does not silently desync this test."""
    keys: set[str] = set()
    for adventure_id, adventure in loaded_campaign.adventures.items():
        for scene in adventure.scenes:
            for placement in scene.placements:
                for ordinal in range(1, placement.count + 1):
                    placement_key = f"{adventure_id}:{scene.id}:{placement.template}:{ordinal}"
                    keys.add(placement_key)
                    for carried in placement.carries:
                        for carried_ordinal in range(1, carried.count + 1):
                            keys.add(f"{placement_key}/{carried.template}:{carried_ordinal}")
    return keys


@pytest.mark.database
def test_ac3_starting_over_greenhollow_v1_writes_exactly_its_declared_objects_unpositioned(
    playthrough_db,
):
    # <- AC3. The `(campaign_run_id, instance_key)` constraint guarantees
    # only that *one run* cannot hold the same authored object twice; it
    # says nothing about how many runs of a campaign a user may have, so a
    # second start of the same campaign must succeed as a second, distinct
    # run with its own complete object set -- not be refused.
    loaded = content_service.load_campaign("greenhollow", "v1")
    expected_keys = _expected_instance_keys(loaded)

    async def _fetch_objects(run_id):
        rows = await playthrough_db.execute(
            text(
                "SELECT id, instance_key, adventure_run_id, scene_id, owner_object_id "
                "FROM objects WHERE campaign_run_id = :run_id"
            ),
            {"run_id": run_id},
        )
        return rows.all()

    async def _scenario():
        user_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO users (id, username, password_hash) "
                "VALUES (:id, :username, :password_hash)"
            ),
            {"id": user_id, "username": "ac3-owner", "password_hash": "not-a-real-hash"},
        )

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )

        # The run pinned its content version.
        stored_version = await playthrough_db.execute(
            text("SELECT content_version FROM campaign_runs WHERE id = :id"), {"id": run.id}
        )
        assert stored_version.scalar_one() == "v1"

        # Exactly the object set the content implies -- no `instance_key`
        # repeated within this one run -- none of it positioned, carried
        # rows pointing at the owner they belong to.
        rows = await _fetch_objects(run.id)
        by_key = {row.instance_key: row for row in rows}
        assert len(rows) == len(expected_keys)  # no instance_key duplicated within the run
        assert set(by_key.keys()) == expected_keys

        for key, row in by_key.items():
            assert row.adventure_run_id is None
            assert row.scene_id is None
            if "/" in key:
                owner_key = key.split("/", 1)[0]
                assert row.owner_object_id == by_key[owner_key].id
            else:
                assert row.owner_object_id is None

        # No event was appended.
        event_count = await playthrough_db.execute(
            text("SELECT count(*) FROM events WHERE campaign_run_id = :run_id"),
            {"run_id": run.id},
        )
        assert event_count.scalar_one() == 0

        # Starting the same campaign again yields a second, distinct run --
        # its own complete set of the thirteen keys, sharing no row with
        # the first run's.
        second_run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )
        assert second_run.id != run.id

        second_rows = await _fetch_objects(second_run.id)
        assert len(second_rows) == len(expected_keys)
        assert {row.instance_key for row in second_rows} == expected_keys
        assert {row.id for row in second_rows}.isdisjoint({row.id for row in rows})

    asyncio.run(_scenario())
