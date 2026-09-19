"""WI1 (sprint 06a): entering the next adventure -- AC1, AC4's service
half. Engine-free throughout, the same way `test_service.py` exercises
`start_campaign_run`: `FakeSession` stands in for `AsyncSession`, and
content loading uses the real shipped `greenhollow/v1` campaign wherever a
single adventure is enough.

`greenhollow/v1` authors exactly one adventure, so it cannot exercise the
"another adventure is already active" refusal (a second call always meets
"nothing left to enter" first -- research.md's open question, settled by
the brief: both refusals ship). `_write_two_trails_campaign` below builds a
second, minimal two-adventure campaign under `tmp_path` for that path
alone, following the idea in `tests/content/conftest.py`'s
`build_version_dir` without importing it -- the two suites' fixtures stay
independent.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import Update
from sqlalchemy.exc import IntegrityError

from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.playthrough import service
from app.modules.playthrough.errors import (
    AdventureActiveError,
    AdventureExhaustedError,
    CampaignRunNotFoundError,
    InvalidRunStatusError,
    RunArchivedError,
)
from app.modules.playthrough.models import AdventureRun, CampaignRun, CampaignRunMember, Event

GREENHOLLOW_ADVENTURE_ID = "goblins-of-greenhollow"
GREENHOLLOW_ENTRY_SCENE = "village-green"


def _load_greenhollow():
    return content_service.load_campaign("greenhollow", "v1")


# --- a minimal two-adventure fixture campaign, for the ADVENTURE_ACTIVE path ---

TWO_TRAILS_CAMPAIGN_ID = "two-trails"
TWO_TRAILS_VERSION = "v1"

_ABILITIES = {
    "strength": 10,
    "dexterity": 10,
    "constitution": 10,
    "intelligence": 10,
    "wisdom": 10,
    "charisma": 14,
}

_ITEM_TEMPLATE = {
    "id": "torch",
    "kind": "item",
    "name": "Torch",
    "description": "A pitch-soaked torch, unlit.",
    "attacks": [],
}

_SEED_CHARACTER = {
    "name": "Traveler",
    "race": "Human",
    "character_class": "Fighter",
    "background": "b",
    "appearance": "a",
    "abilities": _ABILITIES,
    "max_hp": 10,
    "armour_class": 12,
    "inventory": ["torch"],
}


def _trail_scene(scene_id: str) -> dict:
    return {
        "id": scene_id,
        "title": scene_id,
        "truth": ["t"],
        "exits": [{"id": f"{scene_id}-end", "kind": "adventure_end", "description": "d"}],
    }


def _trail_adventure(adventure_id: str, scene_id: str) -> dict:
    return {
        "id": adventure_id,
        "title": adventure_id,
        "intro": "i",
        "entry_scene": scene_id,
        "scenes": [_trail_scene(scene_id)],
    }


def _write_two_trails_campaign(root: Path) -> None:
    """Two adventures, `trail-one` (entry scene `trail-one-scene`) and
    `trail-two` (entry scene `trail-two-scene`), each a single scene with
    no placements and an immediate `adventure_end` exit -- just enough to
    pass `load_campaign`'s content rules (R1-R20) while making
    `uq_adventure_runs_active` reachable in a way `greenhollow` cannot."""
    version_dir = root / "campaigns" / TWO_TRAILS_CAMPAIGN_ID / TWO_TRAILS_VERSION
    (version_dir / "adventures").mkdir(parents=True, exist_ok=True)
    campaign = {
        "id": TWO_TRAILS_CAMPAIGN_ID,
        "title": "Two Trails",
        "summary": "s",
        "adventures": ["trail-one", "trail-two"],
        "seed_character": _SEED_CHARACTER,
        "object_templates": [_ITEM_TEMPLATE],
    }
    (version_dir / "campaign.json").write_text(json.dumps(campaign))
    (version_dir / "adventures" / "trail-one.json").write_text(
        json.dumps(_trail_adventure("trail-one", "trail-one-scene"))
    )
    (version_dir / "adventures" / "trail-two.json").write_text(
        json.dumps(_trail_adventure("trail-two", "trail-two-scene"))
    )


@pytest.fixture
def two_trails_campaign(tmp_path, monkeypatch):
    """Repoints `content_service.CONTENT_ROOT` at a fresh `tmp_path`
    carrying only the two-adventure fixture above -- through the module
    reference, so `monkeypatch.setattr` actually takes effect (D10, same
    as `tests/content/conftest.py`)."""
    monkeypatch.setattr(content_service, "CONTENT_ROOT", tmp_path)
    _write_two_trails_campaign(tmp_path)
    return tmp_path


# --- FakeSession --------------------------------------------------------


class FakeResult:
    """Stands in for the object `AsyncSession.execute()` returns for a
    `select`."""

    def __init__(self, *, scalar=None, scalars=()):
        self._scalar = scalar
        self._scalars = list(scalars)

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars


class FakeSession:
    """Engine-free stand-in for `AsyncSession`, tailored to
    `enter_adventure`.

    `execute()` special-cases an `Update` statement -- `enter_adventure`'s
    two positioning statements -- recording it in `executed_updates` for
    the test to inspect its compiled SQL, rather than treating it as a
    queued `select` result. Every other statement pops the next queued
    `FakeResult`, exactly `test_service.py`'s contract.

    `flush()` assigns an id to anything just added with none (the way a
    column's Python-side default is populated during a real flush) and
    enforces `uq_adventure_runs_active` the way Postgres's partial unique
    index would: a second `AdventureRun` with `status='active'` for a
    campaign run that already holds one raises `IntegrityError` naming
    that constraint in `.orig` -- state persists across calls against the
    same instance, so two `enter_adventure` calls against one `db` can
    observe the real translation without a database.
    """

    def __init__(self, *results, id_generator=generate_id):
        self._results = list(results)
        self._id_generator = id_generator
        self.added: list[object] = []
        self.persisted: list[object] = []
        self.executed_updates: list[Update] = []
        self.committed = 0
        self.rolled_back = 0
        self._active_campaign_run_ids: set[str] = set()

    async def execute(self, stmt):
        if isinstance(stmt, Update):
            self.executed_updates.append(stmt)
            return FakeResult()
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added.extend(objs)

    async def flush(self):
        pending, self.added = self.added, []
        for obj in pending:
            if getattr(obj, "id", None) is None:
                obj.id = self._id_generator()
            if isinstance(obj, AdventureRun) and obj.status == "active":
                if obj.campaign_run_id in self._active_campaign_run_ids:
                    raise IntegrityError(
                        "INSERT INTO adventure_runs",
                        {},
                        Exception("uq_adventure_runs_active"),
                    )
                self._active_campaign_run_ids.add(obj.campaign_run_id)
        self.persisted.extend(pending)

    async def commit(self):
        await self.flush()
        self.committed += 1

    async def rollback(self):
        self.added = []
        self.rolled_back += 1

    async def refresh(self, _obj):
        return None


def _compiled(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _member(run_id="run-1", user_id="user-1") -> CampaignRunMember:
    return CampaignRunMember(campaign_run_id=run_id, user_id=user_id, role="owner")


def _run(run_id="run-1", *, status="ready", campaign_id="greenhollow") -> CampaignRun:
    return CampaignRun(id=run_id, campaign_id=campaign_id, content_version="v1", status=status)


# --- gates: membership, shelf life, status ------------------------------


def test_enter_adventure_raises_not_found_for_a_foreign_run():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))


def test_enter_adventure_raises_run_archived_for_an_archived_run():
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=_run(status="archived")))

    with pytest.raises(RunArchivedError):
        asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))


@pytest.mark.parametrize("status", ["setup", "finished"])
def test_enter_adventure_raises_invalid_run_status_outside_ready_or_active(status):
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=_run(status=status)))

    with pytest.raises(InvalidRunStatusError):
        asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))


# --- the happy path, against the real greenhollow content ---------------


@pytest.mark.parametrize("status", ["ready", "active"])
def test_enter_adventure_inserts_an_active_row_for_the_first_adventure(status):
    db = FakeSession(
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run(status=status)),
        FakeResult(scalars=[]),
    )

    adventure_run = asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    assert adventure_run.campaign_run_id == "run-1"
    assert adventure_run.adventure_id == GREENHOLLOW_ADVENTURE_ID
    assert adventure_run.status == "active"
    assert adventure_run in db.persisted


def test_enter_adventure_does_not_change_the_campaign_run_status():
    # <- D3: the first narration moves the run to `active`, not entry.
    run = _run(status="ready")
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run), FakeResult(scalars=[]))

    asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    assert run.status == "ready"


def test_enter_adventure_positions_the_adventures_cast_excluding_carried_rows():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalars=[])
    )

    adventure_run = asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    cast_update = db.executed_updates[0]
    sql = _compiled(cast_update)
    assert sql.startswith("UPDATE objects SET")
    assert f"adventure_run_id='{adventure_run.id}'" in sql
    assert "scene_id=objects.source_scene_id" in sql
    assert "objects.campaign_run_id = 'run-1'" in sql
    assert f"objects.source_adventure_id = '{GREENHOLLOW_ADVENTURE_ID}'" in sql
    assert "objects.owner_object_id IS NULL" in sql


def test_enter_adventure_positions_every_member_character_at_the_entry_scene():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalars=[])
    )

    adventure_run = asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    character_update = db.executed_updates[1]
    sql = _compiled(character_update)
    assert sql.startswith("UPDATE objects SET")
    assert f"adventure_run_id='{adventure_run.id}'" in sql
    assert f"scene_id='{GREENHOLLOW_ENTRY_SCENE}'" in sql
    assert "objects.campaign_run_id = 'run-1'" in sql
    assert "objects.member_id IS NOT NULL" in sql
    # <- this statement matches on `member_id` alone, precisely so it
    # catches a character created before any adventure existed, which has
    # no `source_adventure_id` for the cast statement to match on.
    assert "source_adventure_id" not in sql


def test_enter_adventure_appends_adventure_started_at_player_visibility():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalars=[])
    )

    adventure_run = asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    events = [obj for obj in db.persisted if isinstance(obj, Event)]
    assert len(events) == 1
    event = events[0]
    assert event.type == "adventure_started"
    assert event.visibility == "player"
    assert event.payload == {"adventureRunId": adventure_run.id}


def test_enter_adventure_commits_exactly_once():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalars=[])
    )

    asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    assert db.committed == 1
    assert db.rolled_back == 0


# --- AC4: nothing left to enter, or re-entering a completed one --------


def test_enter_adventure_raises_exhausted_when_every_adventure_already_has_a_row():
    # <- the query behind "entered" carries no status filter, so a
    # `completed` row for `goblins-of-greenhollow` exhausts it exactly the
    # same way an `active` one would: "nothing left" and "re-entering a
    # completed one" are the same refusal (AC4).
    db = FakeSession(
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run()),
        FakeResult(scalars=[GREENHOLLOW_ADVENTURE_ID]),
    )

    with pytest.raises(AdventureExhaustedError):
        asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    assert db.committed == 0


# --- AC1: a second entry while one is already active --------------------


def test_enter_adventure_translates_the_partial_unique_index_violation(two_trails_campaign):
    run = _run(campaign_id=TWO_TRAILS_CAMPAIGN_ID)
    db = FakeSession(
        FakeResult(scalar=_member()),
        FakeResult(scalar=run),
        FakeResult(scalars=[]),
        FakeResult(scalar=_member()),
        FakeResult(scalar=run),
        FakeResult(scalars=["trail-one"]),
    )

    first = asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))
    assert first.adventure_id == "trail-one"

    with pytest.raises(AdventureActiveError) as excinfo:
        asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    assert isinstance(excinfo.value.__cause__, IntegrityError)
    assert db.committed == 1
    assert db.rolled_back == 1
    # <- the refused attempt appended no second event: only the first
    # call's `adventure_started` ever made it into `persisted`.
    events = [obj for obj in db.persisted if isinstance(obj, Event)]
    assert len(events) == 1


def test_enter_adventure_does_not_swallow_an_unrelated_integrity_error():
    # <- sprint 03's wide catch is the anti-pattern here: only
    # `uq_adventure_runs_active` is translated, so a different constraint
    # violation on the same insert must propagate unchanged.
    class _RaisingSession(FakeSession):
        async def flush(self):
            if any(isinstance(obj, AdventureRun) for obj in self.added):
                raise IntegrityError(
                    "INSERT INTO adventure_runs",
                    {},
                    Exception("uq_adventure_runs_campaign_run_id"),
                )
            await super().flush()

    db = _RaisingSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalars=[])
    )

    with pytest.raises(IntegrityError) as excinfo:
        asyncio.run(service.enter_adventure(db, user_id="user-1", run_id="run-1"))

    assert "uq_adventure_runs_campaign_run_id" in str(excinfo.value.orig)
    assert db.rolled_back == 1
