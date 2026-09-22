"""qa acceptance tests -- sprint 007/02 "run reads for the screens"
(`docs/intents/007-initial-frontend/sprints/02-run-reads-for-screens/brief.md`).

AC1-AC3 are black-box over the wire (`TestClient`, stubbed `db` session):
the pinned `app.modules.playthrough.service` functions the two new routes
call (`list_run_summaries`, `get_run_overview`, I2) are monkeypatched by
attribute the same way every other route-test file in this suite does it
(`tests/playthrough/test_acceptance_campaign_run_starts.py`,
`tests/users/test_routes.py`) -- this file never imports
`app.modules.playthrough.routes` or `.schemas`. Per I2 the routes add no
mapping of their own (the service hands back the wire model directly), so a
`SimpleNamespace` carrying the I3 field set is what FastAPI's own response
serialisation turns into the camelCase body -- exactly as
`test_acceptance_campaign_run_starts.py`'s `_make_run` stands in for
`CampaignRunRead`.

AC4 is different in kind: "no commit, no status change, no event" is a
claim about stored state a faked service could never honestly demonstrate
(a fake just returns data; it proves nothing about what the real one
writes). It carries `@pytest.mark.database` instead, drives the real
`playthrough_service.list_run_summaries` / `get_run_overview` against the
shared scratch-database fixture (`playthrough_db`,
`tests/playthrough/conftest.py`) over a seeded run, and reads the result
back with plain SQL -- the same pattern
`test_acceptance_campaign_run_starts.py`'s AC3 and
`test_acceptance_campaign_run_and_owner.py` use for their own
database-marked checks. The non-member half of AC4 is folded into the same
test: it calls the pre-existing `get_campaign_run` and the new
`get_run_overview` against the identical foreign run and asserts both raise
the identical `CampaignRunNotFoundError` / `NOT_FOUND` (I6, ← D12) -- "the
same as the module's existing reads refuse" proven by comparison, not by
assumption. Skipped under `make backend-test` (no reachable Postgres,
`--no-deps`), run for real under `make backend-test-db`.

AC5 (the regenerated, committed typed client) is a static claim about
`frontend/src/api/schema.d.ts`, not about anything this backend serves; it
lives in the frontend suite instead
(`frontend/src/api/schema.runReads.test.ts`), which can read that file
without ever standing up a server.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): AC4's async calls
are wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts (I1-I6), not against the
service, routes or schemas themselves -- this suite is red until WI1
(the list read) and WI2 (the overview read) land, and green once they do.
"""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

USER_ID = generate_id()


def _stub_auth(monkeypatch, *, user_id: str = USER_ID):
    session = make_session(user_id=user_id)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


def test_ac1_list_answers_campaign_facts_and_counts_newest_first_archived_included(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # <- AC1
    _stub_auth(monkeypatch)

    newer_run = SimpleNamespace(
        id=generate_id(),
        campaign_id="greenhollow",
        status="setup",
        created_at=datetime(2026, 9, 22, 7, 0, 0, tzinfo=UTC),
        campaign_title="Greenhollow",
        campaign_summary="A hedge-village on the edge of the wild.",
        adventures_completed=0,
        adventures_total=1,
        player_count=1,
        unavailable=False,
    )
    older_archived_run = SimpleNamespace(
        id=generate_id(),
        campaign_id="greenhollow",
        status="archived",
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
        campaign_title="Greenhollow",
        campaign_summary="A hedge-village on the edge of the wild.",
        adventures_completed=1,
        adventures_total=1,
        player_count=1,
        unavailable=False,
    )

    async def fake_list(db, *, user_id):
        assert user_id == USER_ID
        # The service is the contract responsible for ordering; the route
        # must simply hand back what it is given, unreordered.
        return [newer_run, older_archived_run]

    monkeypatch.setattr(playthrough_service, "list_run_summaries", fake_list)

    response = client.get(
        "/api/v1/playthrough/runs", headers=session_cookie_header("a-valid-cookie")
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body] == [newer_run.id, older_archived_run.id]
    assert {row["status"] for row in body} == {"setup", "archived"}  # archived run included

    first = body[0]
    assert set(first.keys()) == {
        "id",
        "campaignId",
        "status",
        "createdAt",
        "campaignTitle",
        "campaignSummary",
        "adventuresCompleted",
        "adventuresTotal",
        "playerCount",
        "unavailable",
    }, first
    assert first["campaignId"] == "greenhollow"
    assert first["campaignTitle"] == "Greenhollow"
    assert first["campaignSummary"] == "A hedge-village on the edge of the wild."
    assert first["adventuresCompleted"] == 0
    assert first["adventuresTotal"] == 1
    assert first["unavailable"] is False
    datetime.fromisoformat(first["createdAt"])  # parses; literal spelling is not asserted

    no_auth_response = client.get("/api/v1/playthrough/runs")
    assert_error_envelope(no_auth_response, status=401, code="NOT_AUTHENTICATED")


def test_ac2_run_with_unloadable_content_is_listed_unavailable_with_no_campaign_copy(
    client, monkeypatch, session_cookie_header
):
    # <- AC2
    _stub_auth(monkeypatch)

    broken_run = SimpleNamespace(
        id=generate_id(),
        campaign_id="a-campaign-that-no-longer-loads",
        status="setup",
        created_at=datetime.now(UTC),
        campaign_title=None,
        campaign_summary=None,
        adventures_completed=0,
        adventures_total=None,
        player_count=1,
        unavailable=True,
    )

    async def fake_list(db, *, user_id):
        return [broken_run]

    monkeypatch.setattr(playthrough_service, "list_run_summaries", fake_list)

    response = client.get(
        "/api/v1/playthrough/runs", headers=session_cookie_header("a-valid-cookie")
    )

    # The call succeeds -- nothing raises -- and the run is still present.
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    entry = body[0]
    assert entry["id"] == broken_run.id
    assert entry["unavailable"] is True
    assert entry["campaignTitle"] is None
    assert entry["campaignSummary"] is None
    assert entry["adventuresTotal"] is None
    # The run's own facts (not the content's) are still counted.
    assert entry["adventuresCompleted"] == 0
    assert entry["playerCount"] == 1


def test_ac3_overview_answers_run_members_and_adventures_in_campaign_order(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # <- AC3
    _stub_auth(monkeypatch)
    run_id = generate_id()
    second_member_id = generate_id()

    owner_without_character = SimpleNamespace(
        user_id=USER_ID, username="aragorn", role="owner", ready=False, character=None
    )
    member_with_character = SimpleNamespace(
        user_id=second_member_id,
        username="frodo",
        role="owner",
        ready=True,
        character=SimpleNamespace(
            id=generate_id(),
            name="Rosalind Thorn",
            current_hp=9,
            max_hp=9,
            armour_class=14,
            race="Halfling",
            character_class="Rogue",
            level=1,
            appearance="Barely three feet of him, all elbows and grin.",
        ),
    )
    overview = SimpleNamespace(
        id=run_id,
        campaign_id="greenhollow",
        content_version="v1",
        title=None,
        status="setup",
        created_at=datetime.now(UTC),
        campaign_title="Greenhollow",
        campaign_summary="A hedge-village on the edge of the wild.",
        unavailable=False,
        members=[owner_without_character, member_with_character],
        adventures=[
            SimpleNamespace(
                id="goblins-of-greenhollow",
                title="Goblins of Greenhollow",
                intro_excerpt="Smoke rises over the hedgerows.",
                status="done",
            ),
            SimpleNamespace(
                id="the-hollow-crypt",
                title="The Hollow Crypt",
                intro_excerpt="A cracked barrow door waits in the dark.",
                status="active",
            ),
            SimpleNamespace(
                id="the-last-harvest",
                title="The Last Harvest",
                intro_excerpt="Winter is close and the granary sits empty.",
                status="unplayed",
            ),
        ],
    )

    async def fake_overview(db, *, user_id, run_id):
        assert user_id == USER_ID
        return overview

    monkeypatch.setattr(playthrough_service, "get_run_overview", fake_overview)

    response = client.get(
        f"/api/v1/playthrough/runs/{run_id}/overview",
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == run_id
    assert body["campaignId"] == "greenhollow"
    assert body["campaignTitle"] == "Greenhollow"
    assert body["campaignSummary"] == "A hedge-village on the edge of the wild."
    assert body["unavailable"] is False

    assert len(body["members"]) == 2
    no_character_member, ready_member = body["members"]
    assert set(no_character_member.keys()) == {
        "userId",
        "username",
        "role",
        "ready",
        "character",
    }
    assert no_character_member["username"] == "aragorn"
    assert no_character_member["role"] == "owner"
    assert no_character_member["ready"] is False
    assert no_character_member["character"] is None
    assert ready_member["ready"] is True
    assert ready_member["character"]["name"] == "Rosalind Thorn"
    assert ready_member["character"]["race"] == "Halfling"
    assert ready_member["character"]["characterClass"] == "Rogue"
    assert ready_member["character"]["level"] == 1
    assert ready_member["character"]["appearance"] == (
        "Barely three feet of him, all elbows and grin."
    )

    assert [adventure["id"] for adventure in body["adventures"]] == [
        "goblins-of-greenhollow",
        "the-hollow-crypt",
        "the-last-harvest",
    ]
    assert [adventure["status"] for adventure in body["adventures"]] == [
        "done",
        "active",
        "unplayed",
    ]
    for adventure in body["adventures"]:
        assert set(adventure.keys()) == {"id", "title", "introExcerpt", "status"}

    no_auth_response = client.get(f"/api/v1/playthrough/runs/{run_id}/overview")
    assert_error_envelope(no_auth_response, status=401, code="NOT_AUTHENTICATED")


async def _insert_user(session, user_id: str, username: str) -> None:
    await session.execute(
        text(
            "INSERT INTO users (id, username, password_hash) "
            "VALUES (:id, :username, :password_hash)"
        ),
        {"id": user_id, "username": username, "password_hash": "not-a-real-hash"},
    )


async def _insert_campaign_run(session, run_id: str, *, status: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_runs (id, campaign_id, content_version, status) "
            "VALUES (:id, 'greenhollow', 'v1', :status)"
        ),
        {"id": run_id, "status": status},
    )


async def _insert_member(session, member_id: str, run_id: str, user_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_run_members (id, campaign_run_id, user_id) "
            "VALUES (:id, :campaign_run_id, :user_id)"
        ),
        {"id": member_id, "campaign_run_id": run_id, "user_id": user_id},
    )


@pytest.mark.database
def test_ac4_the_reads_write_nothing_and_refuse_a_non_member_like_the_existing_reads(
    playthrough_db,
):
    # <- AC4
    async def _scenario():
        owner_id = generate_id()
        stranger_id = generate_id()
        await _insert_user(playthrough_db, owner_id, "ac4-owner")
        await _insert_user(playthrough_db, stranger_id, "ac4-stranger")

        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id, status="active")
        await _insert_member(playthrough_db, generate_id(), run_id, owner_id)
        event_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO events (id, campaign_run_id, type, visibility, payload) "
                "VALUES (:id, :run_id, 'narration', 'player', '{}'::jsonb)"
            ),
            {"id": event_id, "run_id": run_id},
        )
        await playthrough_db.commit()

        async def _snapshot():
            status_result = await playthrough_db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": run_id}
            )
            event_count_result = await playthrough_db.execute(
                text("SELECT count(*) FROM events WHERE campaign_run_id = :id"), {"id": run_id}
            )
            member_count_result = await playthrough_db.execute(
                text("SELECT count(*) FROM campaign_run_members WHERE campaign_run_id = :id"),
                {"id": run_id},
            )
            return (
                status_result.scalar_one(),
                event_count_result.scalar_one(),
                member_count_result.scalar_one(),
            )

        before = await _snapshot()

        await playthrough_service.list_run_summaries(playthrough_db, user_id=owner_id)
        await playthrough_service.get_run_overview(playthrough_db, user_id=owner_id, run_id=run_id)

        after = await _snapshot()
        assert after == before  # status unchanged, no event, no membership change

        # A non-member is refused exactly as the module's existing reads
        # refuse: the identical exception type and domain code
        # `get_campaign_run` (unchanged by this sprint) answers for the same
        # foreign run (I6, ← D12).
        with pytest.raises(CampaignRunNotFoundError) as existing_read_error:
            await playthrough_service.get_campaign_run(
                playthrough_db, user_id=stranger_id, run_id=run_id
            )

        with pytest.raises(CampaignRunNotFoundError) as new_read_error:
            await playthrough_service.get_run_overview(
                playthrough_db, user_id=stranger_id, run_id=run_id
            )

        assert new_read_error.value.code == existing_read_error.value.code == ErrorCode.NOT_FOUND

    asyncio.run(_scenario())
