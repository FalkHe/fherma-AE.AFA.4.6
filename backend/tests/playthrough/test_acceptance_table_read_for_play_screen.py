"""qa acceptance tests -- sprint 010/05 "table read" (WI2)
(`docs/intents/010-dm-agent-in-gui/sprints/05-table-read/`).

AC1/AC2 are black-box over the wire (`TestClient`, stubbed `db` session):
the pinned `app.modules.playthrough.service.get_table` the new route calls
(I2) is monkeypatched by attribute, the same way every other route-test
file in this suite does it
(`tests/playthrough/test_acceptance_run_reads_for_screens.py`,
`tests/users/test_routes.py`) -- this file never imports
`app.modules.playthrough.routes` or `.schemas` for that half. Per the
sprint plan the route adds no mapping of its own (the service hands back
the wire model directly), so a `SimpleNamespace` carrying the `TableRead`
field set is what FastAPI's own response serialisation turns into the
camelCase body -- exactly as `test_acceptance_run_reads_for_screens.py`'s
`overview` stands in for `CampaignRunOverviewRead`.

AC3/AC4 drive the real `playthrough_service.get_table` against the shared
scratch-database fixture (`playthrough_db`, `tests/playthrough/conftest.py`)
over a seeded run built from the shipped `greenhollow/v1` content, the same
pattern `test_acceptance_adventures_entered.py`'s AC1 uses to walk a run
from `start_campaign_run` through `create_character` and `enter_adventure`.
AC4 (a foreign run) is folded in alongside AC3, exactly as
`test_acceptance_run_reads_for_screens.py`'s own AC4 compares the new read's
refusal against `get_campaign_run`'s pre-existing one. Skipped under `make
backend-test` (no reachable Postgres, `--no-deps`), run for real under
`make backend-test-db`.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): AC3/AC4's async
calls are wrapped in a single `asyncio.run(...)`.
"""

import asyncio
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

GREENHOLLOW_ADVENTURE_ID = "goblins-of-greenhollow"
GREENHOLLOW_ENTRY_SCENE = "village-green"


def _stub_auth(monkeypatch, *, user_id: str = USER_ID):
    session = make_session(user_id=user_id)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


def _hero() -> SimpleNamespace:
    return SimpleNamespace(
        id=generate_id(),
        name="Rosalind Thorn",
        current_hp=9,
        max_hp=9,
        armour_class=14,
        race="Halfling",
        character_class="Rogue",
        level=1,
        abilities={
            "strength": {"score": 8, "modifier": -1},
            "dexterity": {"score": 16, "modifier": 3},
            "constitution": {"score": 14, "modifier": 2},
            "intelligence": {"score": 12, "modifier": 1},
            "wisdom": {"score": 10, "modifier": 0},
            "charisma": {"score": 13, "modifier": 1},
        },
        appearance="Barely three feet of him, all elbows and grin.",
        backstory="Raised in the kitchens of a river inn.",
        items=[],
    )


def test_ac1_a_run_under_way_names_the_current_adventure_and_the_heros_scene(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # <- AC1
    _stub_auth(monkeypatch)
    run_id = generate_id()

    table = SimpleNamespace(
        run_id=run_id,
        run_title=None,
        run_status="active",
        campaign_title="Greenhollow",
        adventure=SimpleNamespace(
            id=GREENHOLLOW_ADVENTURE_ID,
            run_id=generate_id(),
            title="Goblins of Greenhollow",
            status="active",
        ),
        scene=SimpleNamespace(id=GREENHOLLOW_ENTRY_SCENE, name="Village Green"),
        heroes=[_hero()],
    )

    async def fake_get_table(db, *, user_id, run_id):
        assert user_id == USER_ID
        return table

    monkeypatch.setattr(playthrough_service, "get_table", fake_get_table)

    response = client.get(
        f"/api/v1/playthrough/runs/{run_id}/table",
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {
        "runId",
        "runTitle",
        "runStatus",
        "campaignTitle",
        "adventure",
        "scene",
        "heroes",
    }
    assert body["runId"] == run_id
    assert body["runStatus"] == "active"
    assert body["campaignTitle"] == "Greenhollow"
    assert body["adventure"]["id"] == GREENHOLLOW_ADVENTURE_ID
    assert body["adventure"]["title"] == "Goblins of Greenhollow"
    assert body["adventure"]["status"] == "active"
    assert body["scene"]["id"] == GREENHOLLOW_ENTRY_SCENE
    assert body["scene"]["name"] == "Village Green"
    assert len(body["heroes"]) == 1

    no_auth_response = client.get(f"/api/v1/playthrough/runs/{run_id}/table")
    assert_error_envelope(no_auth_response, status=401, code="NOT_AUTHENTICATED")


def test_ac2_each_seated_hero_carries_its_full_sheet(client, monkeypatch, session_cookie_header):
    # <- AC2
    _stub_auth(monkeypatch)
    run_id = generate_id()

    table = SimpleNamespace(
        run_id=run_id,
        run_title="The Hedge Road",
        run_status="ready",
        campaign_title="Greenhollow",
        adventure=None,
        scene=None,
        heroes=[_hero()],
    )

    async def fake_get_table(db, *, user_id, run_id):
        return table

    monkeypatch.setattr(playthrough_service, "get_table", fake_get_table)

    response = client.get(
        f"/api/v1/playthrough/runs/{run_id}/table",
        headers=session_cookie_header("a-valid-cookie"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["adventure"] is None
    assert body["scene"] is None
    assert len(body["heroes"]) == 1
    hero = body["heroes"][0]
    assert set(hero.keys()) == {
        "id",
        "name",
        "currentHp",
        "maxHp",
        "armourClass",
        "race",
        "characterClass",
        "level",
        "abilities",
        "appearance",
        "backstory",
        "items",
    }
    assert hero["name"] == "Rosalind Thorn"
    assert hero["race"] == "Halfling"
    assert hero["characterClass"] == "Rogue"
    assert hero["level"] == 1
    assert hero["currentHp"] == 9
    assert hero["maxHp"] == 9
    assert hero["armourClass"] == 14
    assert hero["abilities"]["dexterity"] == {"score": 16, "modifier": 3}
    assert hero["appearance"] == "Barely three feet of him, all elbows and grin."
    assert hero["backstory"] == "Raised in the kitchens of a river inn."
    assert hero["items"] == []


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


@pytest.mark.database
def test_ac3_a_turn_that_wounds_the_hero_is_reflected_on_the_next_read(playthrough_db):
    # <- AC3
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac3-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id="greenhollow"
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        adventure_run = await playthrough_service.enter_adventure(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        before = await playthrough_service.get_table(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert before.adventure is not None
        assert before.adventure.id == GREENHOLLOW_ADVENTURE_ID
        assert before.adventure.run_id == adventure_run.id
        assert before.adventure.status == "active"
        assert before.scene is not None
        assert before.scene.id == GREENHOLLOW_ENTRY_SCENE
        assert len(before.heroes) == 1
        assert before.heroes[0].id == character.id
        assert before.heroes[0].current_hp == character.max_hp

        wounded_hp = character.max_hp - 3
        character.current_hp = wounded_hp
        await playthrough_db.commit()

        after = await playthrough_service.get_table(playthrough_db, user_id=owner_id, run_id=run.id)
        assert len(after.heroes) == 1
        assert after.heroes[0].current_hp == wounded_hp
        assert after.heroes[0].max_hp == character.max_hp

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_a_run_the_caller_is_not_seated_at_is_refused_like_the_existing_reads(
    playthrough_db,
):
    # <- AC4
    async def _scenario():
        owner_id = generate_id()
        stranger_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac4-owner")
        await _insert_user(playthrough_db, stranger_id, username="ac4-stranger")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id="greenhollow"
        )

        with pytest.raises(CampaignRunNotFoundError) as existing_read_error:
            await playthrough_service.get_campaign_run(
                playthrough_db, user_id=stranger_id, run_id=run.id
            )

        with pytest.raises(CampaignRunNotFoundError) as new_read_error:
            await playthrough_service.get_table(playthrough_db, user_id=stranger_id, run_id=run.id)

        assert new_read_error.value.code == existing_read_error.value.code == ErrorCode.NOT_FOUND

        with pytest.raises(CampaignRunNotFoundError) as unknown_read_error:
            await playthrough_service.get_table(
                playthrough_db, user_id=owner_id, run_id=generate_id()
            )
        assert unknown_read_error.value.code == ErrorCode.NOT_FOUND

    asyncio.run(_scenario())
