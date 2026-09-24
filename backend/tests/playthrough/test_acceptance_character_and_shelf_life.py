"""qa acceptance tests -- sprint 005/04 "the run gets its character and
becomes playable"
(`docs/intents/005-game-state-services/sprints/04-character-and-shelf-life/brief.md`).

The brief was amended by the product owner after it was written; where they
differ, the amendment wins and is what this file asserts: there is **no
unarchive** (no such endpoint, no such function -- an archived run is kept
only so its story can be re-read); a **finished** run may be archived; and
archiving a run that was never started (`status: "setup"`) **deletes** it --
the run, its membership and its objects -- and answers success.

AC1 and the wire half of AC3 are black-box over the wire (`TestClient`,
stubbed `db` session): the pinned `app.modules.playthrough.service`
functions are monkeypatched, exactly as `test_acceptance_campaign_run_starts
.py` (sprint 005/03) and `tests/auth/test_register.py` do it -- this file
never imports `app.modules.playthrough.routes`, `.schemas` or `.errors`.
Mocked service functions accept `**kwargs` rather than the exact keyword
names of an unread implementation, except where the sprint's own interface
contract fixes them (`create_character(db, *, user_id, run_id, sheet)`).

AC2, the database half of AC3, and AC4 carry `@pytest.mark.database`: they
drive the real `playthrough_service` functions against the shared
scratch-database fixture (`playthrough_db`,
`tests/playthrough/conftest.py`) and read the result back with plain SQL
over `objects` / `campaign_runs` / `campaign_run_members` -- never the ORM
model classes for anything this sprint writes. Every async call in one test
is wrapped in a *single* `asyncio.run(...)`: `AsyncSession`/its underlying
driver connection is bound to the event loop that first used it, so mixing
several independent `asyncio.run()` calls against the same session (or
against a `TestClient` that owns its own loop) within one test is a real
hazard, not a style preference -- this is why the database-backed part of
AC3 drives `rename_campaign_run` / `archive_campaign_run` /
`activate_campaign_run` / `get_campaign_run` / `list_campaign_runs`
directly rather than through `TestClient`.

The seed sheet and inventory are read from the shipped `greenhollow/v1`
content (`app.modules.content.service.load_campaign`) rather than pasted as
literals, so this file survives an authored content change; the sprint's
own contract already tells us Greenhollow's seed pack is five distinct
items, so every carried key ends `:1`.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas).

Written against the sprint's interface contracts, not against the service,
routes or schemas themselves -- this suite is red until the corresponding
work items land, and green once they do.
"""

import asyncio
import json
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


def _make_character(**overrides):
    # Extra attributes (`member_id`, `template_id`, `instance_key`) a real
    # character row would also carry -- included here so AC1's "and nothing
    # else" is a genuine check of the route's response filtering, not an
    # accident of the fake only ever having had the right five fields.
    fields = dict(
        id=generate_id(),
        name="Rosalind Thorn",
        current_hp=12,
        max_hp=12,
        armour_class=15,
        is_alive=True,
        member_id=generate_id(),
        template_id=None,
        instance_key="pc:member-placeholder:1",
        state={
            "abilities": {
                "strength": 10,
                "dexterity": 14,
                "constitution": 12,
                "intelligence": 10,
                "wisdom": 13,
                "charisma": 8,
            },
            "race": "Halfling",
            "character_class": "Rogue",
            "background": "Raised in the kitchens of a river inn.",
            "appearance": "Barely three feet of him, all elbows and grin.",
        },
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text(
            "INSERT INTO users (id, username, password_hash) "
            "VALUES (:id, :username, :password_hash)"
        ),
        {"id": user_id, "username": username, "password_hash": "not-a-real-hash"},
    )


def test_ac1_creating_a_character_reads_it_back_moves_the_run_to_ready_and_refuses_a_second(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    # <- AC1
    _stub_auth(monkeypatch)
    run_id = generate_id()
    character = _make_character()

    async def fake_create_character(db, **kwargs):
        assert kwargs.get("user_id") == USER_ID
        assert kwargs.get("run_id") == run_id
        return character

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    response = client.post(
        f"/api/v1/playthrough/campaign/{run_id}/character",
        headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert set(body.keys()) == {
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
        "down",
    }, body
    assert body["id"] == str(character.id)
    assert body["name"] == character.name
    assert body["currentHp"] == character.current_hp
    assert body["maxHp"] == character.max_hp
    assert body["armourClass"] == character.armour_class

    # The run now reads `ready`.
    ready_run = _make_run(id=run_id, status="ready")

    async def fake_get_ready(db, *, user_id, run_id):
        assert user_id == USER_ID
        return ready_run

    monkeypatch.setattr(playthrough_service, "get_campaign_run", fake_get_ready)

    run_response = client.get(
        f"/api/v1/playthrough/campaign/{run_id}", headers=session_cookie_header("a-valid-cookie")
    )
    assert run_response.status_code == 200, run_response.text
    assert run_response.json()["status"] == "ready"

    # A second call is refused with a stable domain code.
    async def fake_create_character_again(db, **kwargs):
        raise ApiError(ErrorCode.CHARACTER_EXISTS)

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character_again)

    second_response = client.post(
        f"/api/v1/playthrough/campaign/{run_id}/character",
        headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
    )
    assert_error_envelope(second_response, status=409, code="CHARACTER_EXISTS")


@pytest.mark.database
def test_ac2_the_character_and_its_pack_land_as_real_rows_from_the_seed_sheet(playthrough_db):
    # <- AC2
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac2-owner")

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )

        member_id = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM campaign_run_members "
                    "WHERE campaign_run_id = :run_id AND user_id = :user_id"
                ),
                {"run_id": run.id, "user_id": user_id},
            )
        ).scalar_one()

        character = await playthrough_service.create_character(
            playthrough_db, user_id=user_id, run_id=run.id
        )

        sheet = content_service.load_campaign("greenhollow", "v1").campaign.seed_character
        assert len(sheet.inventory) == 5  # Greenhollow's seed pack is five distinct items
        assert len(set(sheet.inventory)) == 5  # every carried key below ends `:1`

        character_row = (
            await playthrough_db.execute(
                text(
                    "SELECT member_id, template_id, instance_key, current_hp, max_hp, "
                    "armour_class, state FROM objects WHERE id = :id"
                ),
                {"id": character.id},
            )
        ).one()

        assert character_row.member_id == member_id
        assert character_row.template_id is None
        assert character_row.instance_key == f"pc:{member_id}:1"
        assert character_row.current_hp == character_row.max_hp == sheet.max_hp
        assert character_row.armour_class == sheet.armour_class

        state = character_row.state
        if isinstance(state, str):
            state = json.loads(state)
        assert state.get("abilities") == sheet.abilities.model_dump()

        carried_rows = (
            await playthrough_db.execute(
                text(
                    "SELECT instance_key, template_id, owner_object_id, adventure_run_id, "
                    "scene_id FROM objects WHERE owner_object_id = :character_id"
                ),
                {"character_id": character.id},
            )
        ).all()

        assert len(carried_rows) == len(sheet.inventory)
        expected_keys = {f"pc:{member_id}:1/{template_id}:1" for template_id in sheet.inventory}
        assert {row.instance_key for row in carried_rows} == expected_keys

        for row in carried_rows:
            assert row.owner_object_id == character.id
            assert row.adventure_run_id is None
            assert row.scene_id is None
            owner_part, item_part = row.instance_key.split("/", 1)
            assert owner_part == f"pc:{member_id}:1"
            template_from_key = item_part.rsplit(":", 1)[0]
            assert row.template_id == template_from_key

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_the_run_can_be_renamed_and_archiving_governs_its_whole_shelf_life(
    client, session_cookie_header, assert_error_envelope, playthrough_db
):
    # <- AC3
    run_id = generate_id()

    # -- Wire contract: rename and archive map onto the right status code
    # and body shape. Scoped to its own `MonkeyPatch` context, not the
    # `monkeypatch` fixture, so every patch made here is guaranteed undone
    # before the real-database scenario below runs the very same service
    # functions for real -- `monkeypatch` only reverts at test teardown, so
    # a patch left standing here would silently shadow the real function
    # the scenario means to call.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)

        renamed_run = _make_run(id=run_id, title="Rosalind's Watch", status="ready")

        async def fake_rename(db, **kwargs):
            return renamed_run

        mp.setattr(playthrough_service, "rename_campaign_run", fake_rename)

        rename_response = client.patch(
            f"/api/v1/playthrough/campaign/{run_id}",
            json={"title": "Rosalind's Watch"},
            headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
        )
        assert rename_response.status_code == 200, rename_response.text
        assert rename_response.json()["title"] == "Rosalind's Watch"

        async def fake_archive(db, **kwargs):
            return None

        mp.setattr(playthrough_service, "archive_campaign_run", fake_archive)

        archive_response = client.post(
            f"/api/v1/playthrough/campaign/{run_id}/archive",
            headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
        )
        assert archive_response.status_code == 204, archive_response.text
        assert archive_response.content == b""

        archived_run = _make_run(id=run_id, status="archived")

        async def fake_get_archived(db, **kwargs):
            return archived_run

        mp.setattr(playthrough_service, "get_campaign_run", fake_get_archived)

        read_after_archive = client.get(
            f"/api/v1/playthrough/campaign/{run_id}",
            headers=session_cookie_header("a-valid-cookie"),
        )
        assert read_after_archive.status_code == 200, read_after_archive.text
        assert read_after_archive.json()["status"] == "archived"

        async def fake_list_still_answers(db, **kwargs):
            return [archived_run]

        mp.setattr(playthrough_service, "list_campaign_runs", fake_list_still_answers)

        list_after_archive = client.get(
            "/api/v1/playthrough/campaign", headers=session_cookie_header("a-valid-cookie")
        )
        assert list_after_archive.status_code == 200, list_after_archive.text
        assert [run["id"] for run in list_after_archive.json()] == [str(run_id)]

    # -- Real database, no monkeypatch in effect: renaming persists,
    # archiving actually moves a ready / active / finished run to
    # `archived`, a genuinely archived run still lists and reads while
    # refusing a rename and a character write with the real domain code --
    # not a stub standing in for the route -- and archiving a run that was
    # never started deletes it outright -- gone from the list and reading
    # it answers not found. All in one `asyncio.run(...)`: see the module
    # docstring for why this scenario never touches `TestClient`.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac3-owner")

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )
        renamed = await playthrough_service.rename_campaign_run(
            playthrough_db, user_id=user_id, run_id=run.id, title="Rosalind's Watch"
        )
        assert renamed.title == "Rosalind's Watch"
        stored_title = await playthrough_db.execute(
            text("SELECT title FROM campaign_runs WHERE id = :id"), {"id": run.id}
        )
        assert stored_title.scalar_one() == "Rosalind's Watch"

        async def _to_ready(candidate):
            await playthrough_service.create_character(
                playthrough_db, user_id=user_id, run_id=candidate.id
            )

        async def _to_active(candidate):
            await _to_ready(candidate)
            await playthrough_service.activate_campaign_run(
                playthrough_db, user_id=user_id, run_id=candidate.id
            )

        async def _to_finished(candidate):
            # A real "finished" run always already has a character -- it
            # got there by being played, not by skipping straight from
            # `setup`. Forcing the status column alone, with no character,
            # would look to the service like a never-started run.
            await _to_ready(candidate)
            await playthrough_db.execute(
                text("UPDATE campaign_runs SET status = 'finished' WHERE id = :id"),
                {"id": candidate.id},
            )

        for reach_status in (_to_ready, _to_active, _to_finished):
            candidate = await playthrough_service.start_campaign_run(
                playthrough_db, user_id=user_id, campaign_id="greenhollow"
            )
            await reach_status(candidate)
            await playthrough_service.archive_campaign_run(
                playthrough_db, user_id=user_id, run_id=candidate.id
            )
            status = await playthrough_db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": candidate.id}
            )
            assert status.scalar_one() == "archived"

        # A genuinely archived run: still listed and readable, but refuses
        # a rename and a character write, both with the same domain code.
        archived_candidate = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )
        await playthrough_service.create_character(
            playthrough_db, user_id=user_id, run_id=archived_candidate.id
        )
        await playthrough_service.archive_campaign_run(
            playthrough_db, user_id=user_id, run_id=archived_candidate.id
        )

        archived_read = await playthrough_service.get_campaign_run(
            playthrough_db, user_id=user_id, run_id=archived_candidate.id
        )
        assert archived_read.status == "archived"

        listed_runs = await playthrough_service.list_campaign_runs(playthrough_db, user_id=user_id)
        assert archived_candidate.id in {r.id for r in listed_runs}

        # Calling the service directly raises its own domain exception, not
        # `ApiError` (that translation happens in the route layer this test
        # never imports) -- caught here by its one contractual trait, the
        # `.code` the interface promises, rather than by importing the
        # forbidden `playthrough/errors.py` to name the class.
        with pytest.raises(Exception) as rename_exc:
            await playthrough_service.rename_campaign_run(
                playthrough_db, user_id=user_id, run_id=archived_candidate.id, title="New Name"
            )
        assert rename_exc.value.code == ErrorCode.RUN_ARCHIVED

        with pytest.raises(Exception) as character_exc:
            await playthrough_service.create_character(
                playthrough_db, user_id=user_id, run_id=archived_candidate.id
            )
        assert character_exc.value.code == ErrorCode.RUN_ARCHIVED

        # A never-started run is deleted outright: gone from the list and
        # reads as not found, its membership and objects gone with it.
        setup_run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )
        object_count_before = await playthrough_db.execute(
            text("SELECT count(*) FROM objects WHERE campaign_run_id = :id"),
            {"id": setup_run.id},
        )
        assert object_count_before.scalar_one() > 0  # the world was instantiated on start

        await playthrough_service.archive_campaign_run(
            playthrough_db, user_id=user_id, run_id=setup_run.id
        )

        remaining_runs = await playthrough_service.list_campaign_runs(
            playthrough_db, user_id=user_id
        )
        assert setup_run.id not in {r.id for r in remaining_runs}

        with pytest.raises(Exception) as exc_info:
            await playthrough_service.get_campaign_run(
                playthrough_db, user_id=user_id, run_id=setup_run.id
            )
        assert exc_info.value.code == ErrorCode.NOT_FOUND

        remaining_run_row = await playthrough_db.execute(
            text("SELECT id FROM campaign_runs WHERE id = :id"), {"id": setup_run.id}
        )
        assert remaining_run_row.first() is None
        remaining_member_row = await playthrough_db.execute(
            text("SELECT id FROM campaign_run_members WHERE campaign_run_id = :id"),
            {"id": setup_run.id},
        )
        assert remaining_member_row.first() is None
        remaining_object_row = await playthrough_db.execute(
            text("SELECT id FROM objects WHERE campaign_run_id = :id"), {"id": setup_run.id}
        )
        assert remaining_object_row.first() is None

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_activating_a_run_is_a_service_only_transition_reachable_by_no_route(
    client, playthrough_db
):
    # <- AC4
    assert callable(playthrough_service.activate_campaign_run)

    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac4-owner")

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )
        await playthrough_service.create_character(playthrough_db, user_id=user_id, run_id=run.id)

        await playthrough_service.activate_campaign_run(
            playthrough_db, user_id=user_id, run_id=run.id
        )

        status_row = await playthrough_db.execute(
            text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": run.id}
        )
        assert status_row.scalar_one() == "active"

    asyncio.run(_scenario())

    # No route reaches it: the published API surface names no activation
    # endpoint or operation anywhere under the playthrough prefix.
    openapi = client.get("/openapi.json").json()
    playthrough_paths = {
        path: methods for path, methods in openapi["paths"].items() if "/playthrough/" in path
    }
    assert playthrough_paths, "expected the playthrough routes to be registered"
    assert "activate" not in str(playthrough_paths).lower()
