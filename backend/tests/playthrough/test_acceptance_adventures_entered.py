"""qa acceptance tests -- sprint 005/06a "an adventure is entered and its
world takes its places"
(`docs/intents/005-game-state-services/sprints/06a-adventures-entered/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`,
`.routes` or `.errors` themselves -- those are this sprint's own work
items, written in parallel, and this file never imports or reads them.

Each criterion's wire half (the 201 shape, authentication, CSRF, and the
409 envelope for each new domain code) is exercised through `client` with a
stubbed `db` session and a monkeypatched `app.modules.playthrough.service`,
scoped to its own `MonkeyPatch.context()`, exactly as
`test_acceptance_campaign_run_starts.py` and
`test_acceptance_transcript_writer_and_read.py` do it. Each criterion's
database half -- what the stored world looks like afterwards -- drives the
real `playthrough_service` functions directly against the shared
scratch-database fixture (`playthrough_db`,
`tests/playthrough/conftest.py`) and reads the result back with plain SQL
over `objects` / `adventure_runs` / `events` / `campaign_runs`, never the
ORM model classes. Mixing `TestClient` and a real `AsyncSession` in one
test is a documented hazard in this suite
(`test_acceptance_adventure_progress.py`'s module docstring), which is why
the two halves of every test below never touch the same session.

AC1's "a second entry while one is active" refusal is, by the sprint's own
plan, only reachable in a campaign that authors two or more adventures --
with the shipped one-adventure `greenhollow`, the "nothing left to enter"
refusal always answers first. That test therefore builds its own small
fixture campaign on disk (`_write_two_adventure_campaign`) and repoints
`app.modules.content.service.CONTENT_ROOT` at it through the module
reference, the same way `tests/content/conftest.py`'s `content_root`
fixture does (`monkeypatch.setattr(service, "CONTENT_ROOT", ...)`, never a
name import, so the patch cannot silently miss). The other two criteria
need only the shipped `greenhollow/v1` content and are driven against it
directly.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
in one test is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service,
routes or errors themselves -- this suite is red until the corresponding
work items land, and green once they do.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
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

GREENHOLLOW_ADVENTURE_ID = "goblins-of-greenhollow"
GREENHOLLOW_ENTRY_SCENE = "village-green"

# The fixture campaign AC1's "second entry" scenario needs: two adventures,
# each a single scene that ends the adventure immediately, so entering the
# first, then attempting to enter again while it is still active, is the
# only thing either adventure is authored to test.
CAMPAIGN_ID = "twin-vales"
CAMPAIGN_VERSION = "v1"
FIRST_ADVENTURE_ID = "first-vale"
SECOND_ADVENTURE_ID = "second-vale"
FIRST_ENTRY_SCENE = "first-vale-camp"
SECOND_ENTRY_SCENE = "second-vale-camp"
FIRST_CREATURE_TEMPLATE = "vale-warden"
FIRST_CARRIED_TEMPLATE = "vale-token"
SECOND_CREATURE_TEMPLATE = "vale-sentinel"
SEED_ITEM_TEMPLATE = "travelers-pack"


def _stub_auth(monkeypatch, *, user_id: str = USER_ID, csrf_token: str = CSRF_TOKEN):
    session = make_session(user_id=user_id, csrf_token=csrf_token)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


def _abilities() -> dict:
    return {
        "strength": 10,
        "dexterity": 10,
        "constitution": 10,
        "intelligence": 10,
        "wisdom": 10,
        "charisma": 10,
    }


def _creature_template(template_id: str, name: str) -> dict:
    return {
        "id": template_id,
        "kind": "creature",
        "name": name,
        "description": f"{name}, a fixture creature for the adventures-entered acceptance suite.",
        "disposition": "Watchful and otherwise unremarkable.",
        "stat_block": {
            "max_hp": 5,
            "armour_class": 10,
            "abilities": _abilities(),
            "attacks": [],
            "traits": [],
        },
    }


def _item_template(template_id: str, name: str) -> dict:
    return {
        "id": template_id,
        "kind": "item",
        "name": name,
        "description": f"{name}, a fixture item for the adventures-entered acceptance suite.",
        "attacks": [],
    }


def _one_scene_adventure(
    *, adventure_id: str, entry_scene: str, creature_template: str, carried_template: str | None
) -> dict:
    placement: dict = {"template": creature_template, "count": 1}
    if carried_template is not None:
        placement["carries"] = [{"template": carried_template, "count": 1}]
    return {
        "id": adventure_id,
        "title": adventure_id.replace("-", " ").title(),
        "intro": f"A fixture adventure, {adventure_id}.",
        "entry_scene": entry_scene,
        "scenes": [
            {
                "id": entry_scene,
                "title": entry_scene.replace("-", " ").title(),
                "truth": [f"A fixture truth about {entry_scene}."],
                "npc_intent": None,
                "consequences": [],
                "hidden": [],
                "placements": [placement],
                "exits": [
                    {
                        "id": f"leave-{adventure_id}",
                        "kind": "adventure_end",
                        "description": "A fixture way out, ending the adventure at once.",
                        "condition": None,
                    }
                ],
            }
        ],
    }


def _write_two_adventure_campaign(root: Path) -> None:
    """Writes `CAMPAIGN_ID/CAMPAIGN_VERSION` under `root/campaigns/`: two
    adventures, each one scene deep, so a game can be walked straight from
    `setup` to "the first adventure is active" in the fewest possible
    service calls."""
    version_dir = root / "campaigns" / CAMPAIGN_ID / CAMPAIGN_VERSION
    (version_dir / "adventures").mkdir(parents=True, exist_ok=True)

    campaign = {
        "id": CAMPAIGN_ID,
        "title": "Twin Vales",
        "summary": "A fixture campaign authoring two adventures, for the adventures-entered suite.",
        "adventures": [FIRST_ADVENTURE_ID, SECOND_ADVENTURE_ID],
        "seed_character": {
            "name": "Fixture Wanderer",
            "race": "Human",
            "character_class": "Fighter",
            "background": "A fixture background, written for this suite alone.",
            "appearance": "A fixture appearance, written for this suite alone.",
            "abilities": _abilities(),
            "max_hp": 8,
            "armour_class": 12,
            "inventory": [SEED_ITEM_TEMPLATE],
        },
        "object_templates": [
            _creature_template(FIRST_CREATURE_TEMPLATE, "Vale Warden"),
            _item_template(FIRST_CARRIED_TEMPLATE, "Vale Token"),
            _creature_template(SECOND_CREATURE_TEMPLATE, "Vale Sentinel"),
            _item_template(SEED_ITEM_TEMPLATE, "Traveler's Pack"),
        ],
    }
    (version_dir / "campaign.json").write_text(json.dumps(campaign, indent=2))

    first_adventure = _one_scene_adventure(
        adventure_id=FIRST_ADVENTURE_ID,
        entry_scene=FIRST_ENTRY_SCENE,
        creature_template=FIRST_CREATURE_TEMPLATE,
        carried_template=FIRST_CARRIED_TEMPLATE,
    )
    second_adventure = _one_scene_adventure(
        adventure_id=SECOND_ADVENTURE_ID,
        entry_scene=SECOND_ENTRY_SCENE,
        creature_template=SECOND_CREATURE_TEMPLATE,
        carried_template=None,
    )
    (version_dir / "adventures" / f"{FIRST_ADVENTURE_ID}.json").write_text(
        json.dumps(first_adventure, indent=2)
    )
    (version_dir / "adventures" / f"{SECOND_ADVENTURE_ID}.json").write_text(
        json.dumps(second_adventure, indent=2)
    )


def test_ac1_entering_answers_the_run_positions_the_world_and_records_the_start(
    client, session_cookie_header, assert_error_envelope, playthrough_db
):
    # <- AC1
    wire_run_id = generate_id()

    # -- Wire contract: 201 with exactly the four camelCase keys; the call
    # requires authentication and the CSRF header; a foreign-or-unknown
    # game answers `NOT_FOUND`. Scoped to its own `MonkeyPatch.context()`
    # so nothing here leaks into the real-database scenario below.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)

        fake_run = SimpleNamespace(
            id=generate_id(),
            adventure_id=GREENHOLLOW_ADVENTURE_ID,
            status="active",
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        async def fake_enter(db, *, user_id, run_id):
            assert user_id == USER_ID
            assert run_id == wire_run_id
            return fake_run

        mp.setattr(playthrough_service, "enter_adventure", fake_enter)

        response = client.post(
            f"/api/v1/playthrough/campaign/{wire_run_id}/adventure",
            headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert set(body.keys()) == {"id", "adventureId", "status", "startedAt"}, body
        assert body["id"] == str(fake_run.id)
        assert body["adventureId"] == GREENHOLLOW_ADVENTURE_ID
        assert body["status"] == "active"
        datetime.fromisoformat(body["startedAt"])  # parses; literal spelling is not asserted

        no_auth_response = client.post(f"/api/v1/playthrough/campaign/{wire_run_id}/adventure")
        assert_error_envelope(no_auth_response, status=401, code="NOT_AUTHENTICATED")

        no_csrf_response = client.post(
            f"/api/v1/playthrough/campaign/{wire_run_id}/adventure",
            headers=session_cookie_header("a-valid-cookie"),
        )
        assert_error_envelope(no_csrf_response, status=403, code="CSRF_TOKEN_INVALID")

        async def fake_enter_not_found(db, *, user_id, run_id):
            raise ApiError(ErrorCode.NOT_FOUND)

        mp.setattr(playthrough_service, "enter_adventure", fake_enter_not_found)
        unknown_response = client.post(
            f"/api/v1/playthrough/campaign/{generate_id()}/adventure",
            headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
        )
        assert_error_envelope(unknown_response, status=404, code="NOT_FOUND")

    # -- Real database, no monkeypatch in effect: entering the shipped
    # `greenhollow` adventure positions its cast where the content places
    # them (not all forced to the entry scene -- Greenhollow's placements
    # span four different scenes), positions the character at the entry
    # scene, leaves carried items untouched, does not touch the campaign
    # run's own status, and appends exactly one `adventure_started` entry
    # naming the new adventure run. A foreign or an unknown run both answer
    # `NOT_FOUND`, indistinguishably.
    async def _scenario():
        owner_id = generate_id()
        stranger_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac1-owner")
        await _insert_user(playthrough_db, stranger_id, username="ac1-stranger")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id="greenhollow"
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        cast_rows_before = (
            await playthrough_db.execute(
                text(
                    "SELECT id, source_scene_id FROM objects WHERE campaign_run_id = :run_id "
                    "AND source_adventure_id IS NOT NULL AND owner_object_id IS NULL"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(cast_rows_before) > 0
        assert len({row.source_scene_id for row in cast_rows_before}) > 1  # spans several scenes

        carried_rows_before = (
            await playthrough_db.execute(
                text(
                    "SELECT id, owner_object_id FROM objects WHERE campaign_run_id = :run_id "
                    "AND owner_object_id IS NOT NULL"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(carried_rows_before) > 0

        adventure_run = await playthrough_service.enter_adventure(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert adventure_run.status == "active"
        assert adventure_run.started_at is not None
        assert adventure_run.adventure_id == GREENHOLLOW_ADVENTURE_ID

        # The campaign run's own status is untouched by entering.
        run_status = (
            await playthrough_db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": run.id}
            )
        ).scalar_one()
        assert run_status == "ready"

        # The cast lands where the content places it -- each row's own
        # `source_scene_id`, not uniformly the entry scene.
        for row in cast_rows_before:
            positioned = (
                await playthrough_db.execute(
                    text("SELECT adventure_run_id, scene_id FROM objects WHERE id = :id"),
                    {"id": row.id},
                )
            ).one()
            assert positioned.adventure_run_id == adventure_run.id
            assert positioned.scene_id == row.source_scene_id

        # The character lands at the adventure's entry scene.
        character_position = (
            await playthrough_db.execute(
                text("SELECT adventure_run_id, scene_id FROM objects WHERE id = :id"),
                {"id": character.id},
            )
        ).one()
        assert character_position.adventure_run_id == adventure_run.id
        assert character_position.scene_id == GREENHOLLOW_ENTRY_SCENE

        # Carried items stay with their owners -- still unpositioned.
        for row in carried_rows_before:
            carried_after = (
                await playthrough_db.execute(
                    text(
                        "SELECT owner_object_id, adventure_run_id, scene_id "
                        "FROM objects WHERE id = :id"
                    ),
                    {"id": row.id},
                )
            ).one()
            assert carried_after.owner_object_id == row.owner_object_id
            assert carried_after.adventure_run_id is None
            assert carried_after.scene_id is None

        # Nothing else was moved: exactly the cast plus the one character
        # now carry a position.
        positioned_count = (
            await playthrough_db.execute(
                text(
                    "SELECT count(*) FROM objects WHERE campaign_run_id = :run_id "
                    "AND adventure_run_id IS NOT NULL"
                ),
                {"run_id": run.id},
            )
        ).scalar_one()
        assert positioned_count == len(cast_rows_before) + 1

        # The transcript records that the adventure began, visible to the
        # player, naming this adventure run.
        started_events = (
            await playthrough_db.execute(
                text(
                    "SELECT visibility, payload FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'adventure_started'"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(started_events) == 1
        event = started_events[0]
        assert event.visibility == "player"
        payload = event.payload
        if isinstance(payload, str):
            payload = json.loads(payload)
        assert payload.get("adventureRunId") == str(adventure_run.id)

        # A foreign or an unknown run both answer `NOT_FOUND`, alike.
        with pytest.raises(Exception) as unknown_exc:
            await playthrough_service.enter_adventure(
                playthrough_db, user_id=owner_id, run_id=generate_id()
            )
        assert unknown_exc.value.code == ErrorCode.NOT_FOUND

        with pytest.raises(Exception) as foreign_exc:
            await playthrough_service.enter_adventure(
                playthrough_db, user_id=stranger_id, run_id=run.id
            )
        assert foreign_exc.value.code == ErrorCode.NOT_FOUND

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac1_entering_again_while_one_is_active_is_refused_with_its_own_code(
    client, session_cookie_header, assert_error_envelope, playthrough_db, tmp_path, monkeypatch
):
    # <- AC1 (second entry): only reachable in a campaign authoring two or
    # more adventures (plan.md's own note), hence the fixture campaign
    # built on disk above rather than the shipped, single-adventure
    # `greenhollow`.

    # -- Wire contract: the envelope for this refusal's own domain code.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)

        async def fake_active(db, *, user_id, run_id):
            raise ApiError(ErrorCode.ADVENTURE_ACTIVE)

        mp.setattr(playthrough_service, "enter_adventure", fake_active)

        response = client.post(
            f"/api/v1/playthrough/campaign/{generate_id()}/adventure",
            headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
        )
        assert_error_envelope(response, status=409, code="ADVENTURE_ACTIVE")

    # -- Real database: the fixture campaign is written before anything
    # touches `content_service.CONTENT_ROOT`, then the module reference is
    # repointed at it (never a name import -- `tests/content/conftest.py`'s
    # own `content_root` fixture does it the same way, for the same reason).
    _write_two_adventure_campaign(tmp_path)
    monkeypatch.setattr(content_service, "CONTENT_ROOT", tmp_path)

    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac1-second-entry-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        await playthrough_service.create_character(playthrough_db, user_id=user_id, run_id=run.id)

        first = await playthrough_service.enter_adventure(
            playthrough_db, user_id=user_id, run_id=run.id
        )
        assert first.adventure_id == FIRST_ADVENTURE_ID
        assert first.status == "active"

        with pytest.raises(Exception) as exc_info:
            await playthrough_service.enter_adventure(
                playthrough_db, user_id=user_id, run_id=run.id
            )
        assert exc_info.value.code == ErrorCode.ADVENTURE_ACTIVE

        # The refusal left nothing behind: still exactly the one active
        # adventure run, and exactly one `adventure_started` entry.
        rows = (
            await playthrough_db.execute(
                text("SELECT adventure_id, status FROM adventure_runs WHERE campaign_run_id = :id"),
                {"id": run.id},
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].adventure_id == FIRST_ADVENTURE_ID
        assert rows[0].status == "active"

        started_events = (
            await playthrough_db.execute(
                text(
                    "SELECT count(*) FROM events WHERE campaign_run_id = :id "
                    "AND type = 'adventure_started'"
                ),
                {"id": run.id},
            )
        ).scalar_one()
        assert started_events == 1

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_entering_with_nothing_left_to_enter_is_refused_with_the_other_code(
    client, session_cookie_header, assert_error_envelope, playthrough_db
):
    # <- AC4: with the shipped, single-adventure `greenhollow`, marking its
    # one adventure run completed puts the game in both states the
    # criterion names at once -- "every adventure completed" and
    # "re-entering one already completed" coincide exactly when there is
    # only one. Nothing in this sprint's own scope can complete an
    # adventure (`use_exit` is 06b's), so that transition is reached
    # directly against the row this sprint's own service just wrote,
    # exactly as `test_acceptance_character_and_shelf_life.py`'s `_to_finished`
    # forces `campaign_runs.status` directly for the same reason.

    # -- Wire contract: the envelope for this refusal's own domain code.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)

        async def fake_exhausted(db, *, user_id, run_id):
            raise ApiError(ErrorCode.ADVENTURE_EXHAUSTED)

        mp.setattr(playthrough_service, "enter_adventure", fake_exhausted)

        response = client.post(
            f"/api/v1/playthrough/campaign/{generate_id()}/adventure",
            headers={**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": CSRF_TOKEN},
        )
        assert_error_envelope(response, status=409, code="ADVENTURE_EXHAUSTED")

    # -- Real database.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ac4-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id="greenhollow"
        )
        await playthrough_service.create_character(playthrough_db, user_id=user_id, run_id=run.id)

        entered = await playthrough_service.enter_adventure(
            playthrough_db, user_id=user_id, run_id=run.id
        )
        assert entered.adventure_id == GREENHOLLOW_ADVENTURE_ID

        await playthrough_db.execute(
            text(
                "UPDATE adventure_runs SET status = 'completed', completed_at = now() "
                "WHERE id = :id"
            ),
            {"id": entered.id},
        )
        await playthrough_db.commit()

        with pytest.raises(Exception) as exc_info:
            await playthrough_service.enter_adventure(
                playthrough_db, user_id=user_id, run_id=run.id
            )
        assert exc_info.value.code == ErrorCode.ADVENTURE_EXHAUSTED

        # The refusal wrote nothing: still exactly the one (now completed)
        # adventure run, and no second `adventure_started` entry.
        remaining = (
            await playthrough_db.execute(
                text("SELECT count(*) FROM adventure_runs WHERE campaign_run_id = :id"),
                {"id": run.id},
            )
        ).scalar_one()
        assert remaining == 1

        started_events = (
            await playthrough_db.execute(
                text(
                    "SELECT count(*) FROM events WHERE campaign_run_id = :id "
                    "AND type = 'adventure_started'"
                ),
                {"id": run.id},
            )
        ).scalar_one()
        assert started_events == 1

    asyncio.run(_scenario())
