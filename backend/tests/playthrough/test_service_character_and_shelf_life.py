"""WI1: the character write and its inventory, renaming, archiving (which
deletes a never-started run), `activate_campaign_run`, and the
`_require_writable` gate an archived run puts in front of every write
(AC1-AC4's service half). Engine-free throughout, same `FakeSession`
pattern as `test_service.py`: `execute()` returns queued results, `add`/
`add_all`/`flush`/`delete`/`commit` simulate just enough of SQLAlchemy's
unit of work. Content loading uses the real shipped `greenhollow/v1`
campaign (`content.service` only touches the filesystem, never a
database), so no fixture campaign is needed here.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio

import pytest

from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.playthrough import service
from app.modules.playthrough.errors import (
    CampaignRunNotFoundError,
    CharacterExistsError,
    CharacterNotFoundError,
    InvalidRunStatusError,
    RunArchivedError,
)
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, GameObject

GREENHOLLOW_SEED = content_service.load_campaign("greenhollow", "v1").campaign.seed_character


def _run(*, run_id="run-1", status="setup", campaign_id="greenhollow", content_version="v1"):
    return CampaignRun(
        id=run_id, campaign_id=campaign_id, content_version=content_version, status=status
    )


def _member(*, member_id="member-1", run_id="run-1", user_id="user-1"):
    return CampaignRunMember(id=member_id, campaign_run_id=run_id, user_id=user_id, role="owner")


class FakeResult:
    """Stands in for the object `AsyncSession.execute()` returns."""

    def __init__(self, *, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    """Engine-free stand-in for `AsyncSession` (same shape as
    `test_service.py`'s, plus `delete()` for archiving a never-started
    run)."""

    def __init__(self, *results):
        self._results = list(results)
        self.added: list[object] = []
        self.persisted: list[object] = []
        self.deleted: list[object] = []
        self.committed = 0

    async def execute(self, _stmt):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added.extend(objs)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        pending, self.added = self.added, []
        for obj in pending:
            if getattr(obj, "id", None) is None:
                obj.id = generate_id()
        self.persisted.extend(pending)

    async def commit(self):
        await self.flush()
        self.committed += 1

    async def refresh(self, _obj):
        return None


# --- _require_writable ---------------------------------------------------


def test_require_writable_raises_run_archived_when_the_run_is_archived():
    run = _run(status="archived")

    with pytest.raises(RunArchivedError):
        service._require_writable(run)


@pytest.mark.parametrize("status", ["setup", "ready", "active", "finished"])
def test_require_writable_is_silent_for_every_other_status(status):
    service._require_writable(_run(status=status))


# --- create_character ------------------------------------------------------


def test_create_character_reads_the_pinned_seed_when_no_sheet_is_given():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(
        service.create_character(db, user_id="user-1", run_id="run-1", sheet=None)
    )

    assert character.name == GREENHOLLOW_SEED.name


def test_create_character_sets_member_id_and_no_template():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))

    assert character.member_id == "member-1"
    assert character.template_id is None
    assert character.kind == "creature"


def test_create_character_key_is_pc_member_id_1():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))

    assert character.instance_key == "pc:member-1:1"


def test_create_character_sets_hp_and_armour_from_the_sheet():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))

    assert character.current_hp == character.max_hp == GREENHOLLOW_SEED.max_hp
    assert character.armour_class == GREENHOLLOW_SEED.armour_class
    assert character.is_alive is True


def test_create_character_writes_state_whole_from_the_sheet():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))

    assert character.state == {
        "abilities": GREENHOLLOW_SEED.abilities.model_dump(),
        "race": GREENHOLLOW_SEED.race,
        "character_class": GREENHOLLOW_SEED.character_class,
        "background": GREENHOLLOW_SEED.background,
        "appearance": GREENHOLLOW_SEED.appearance,
        "down": False,  # sprint 09, WI1: a character starts not down.
        # sprint 009-02, WI2: a built sheet's own fields, defaulted here --
        # the seed path writes exactly what it wrote before.
        "level": 1,
        "alignment": None,
        "speed": 30,
        "proficiency_bonus": 2,
        "saving_throws": [],
        "skills": [],
        "equipment": [],
    }


def test_create_character_uses_a_given_sheet_instead_of_the_pinned_seed():
    sheet = GREENHOLLOW_SEED.model_copy(update={"name": "Custom Hero"})
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(
        service.create_character(db, user_id="user-1", run_id="run-1", sheet=sheet)
    )

    assert character.name == "Custom Hero"


def test_create_character_builds_one_carried_row_per_seed_inventory_entry():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))

    carried = [obj for obj in db.persisted if isinstance(obj, GameObject) and obj is not character]
    assert {obj.instance_key for obj in carried} == {
        f"pc:member-1:1/{template_id}:1" for template_id in GREENHOLLOW_SEED.inventory
    }
    assert all(obj.owner_object_id == character.id for obj in carried)
    assert all(obj.adventure_run_id is None and obj.scene_id is None for obj in carried)


def test_create_character_counts_repeats_of_the_same_template_within_the_pack():
    sheet = GREENHOLLOW_SEED.model_copy(
        update={"inventory": ["shepherds-knife", "shepherds-knife", "rations"]}
    )
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    character = asyncio.run(
        service.create_character(db, user_id="user-1", run_id="run-1", sheet=sheet)
    )

    carried = [obj for obj in db.persisted if isinstance(obj, GameObject) and obj is not character]
    assert {obj.instance_key for obj in carried} == {
        "pc:member-1:1/shepherds-knife:1",
        "pc:member-1:1/shepherds-knife:2",
        "pc:member-1:1/rations:1",
    }


def test_create_character_moves_the_run_to_ready():
    run = _run()
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run), FakeResult(scalar=None))

    asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))

    assert run.status == "ready"


def test_create_character_commits_once_and_appends_no_event():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar=None)
    )

    asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))

    assert db.committed == 1
    kinds = {type(obj).__name__ for obj in db.persisted}
    assert kinds == {"GameObject"}


def test_create_character_refuses_a_second_character_on_the_same_run():
    db = FakeSession(
        FakeResult(scalar=_member()), FakeResult(scalar=_run()), FakeResult(scalar="already-exists")
    )

    with pytest.raises(CharacterExistsError):
        asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))


def test_create_character_refuses_an_archived_run():
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=_run(status="archived")))

    with pytest.raises(RunArchivedError):
        asyncio.run(service.create_character(db, user_id="user-1", run_id="run-1"))


# --- rename_campaign_run ---------------------------------------------------


def test_rename_campaign_run_sets_the_title():
    run = _run(status="ready")
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run))

    result = asyncio.run(
        service.rename_campaign_run(db, user_id="user-1", run_id="run-1", title="New Title")
    )

    assert result is run
    assert run.title == "New Title"
    assert db.committed == 1


def test_rename_campaign_run_refuses_an_archived_run():
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=_run(status="archived")))

    with pytest.raises(RunArchivedError):
        asyncio.run(
            service.rename_campaign_run(db, user_id="user-1", run_id="run-1", title="New Title")
        )


# --- archive_campaign_run ---------------------------------------------------


@pytest.mark.parametrize("status", ["ready", "active", "finished"])
def test_archive_campaign_run_moves_to_archived(status):
    run = _run(status=status)
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run))

    asyncio.run(service.archive_campaign_run(db, user_id="user-1", run_id="run-1"))

    assert run.status == "archived"
    assert db.committed == 1
    assert db.deleted == []


def test_archive_campaign_run_deletes_a_never_started_run():
    run = _run(status="setup")
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run))

    asyncio.run(service.archive_campaign_run(db, user_id="user-1", run_id="run-1"))

    assert db.deleted == [run]
    assert db.committed == 1


def test_archive_campaign_run_is_a_no_op_when_already_archived():
    run = _run(status="archived")
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run))

    asyncio.run(service.archive_campaign_run(db, user_id="user-1", run_id="run-1"))

    assert run.status == "archived"
    assert db.deleted == []
    assert db.committed == 0


# --- activate_campaign_run ---------------------------------------------------


def test_activate_campaign_run_moves_ready_to_active():
    run = _run(status="ready")
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run))

    result = asyncio.run(service.activate_campaign_run(db, user_id="user-1", run_id="run-1"))

    assert result is run
    assert run.status == "active"
    assert db.committed == 1


def test_activate_campaign_run_is_a_no_op_when_already_active():
    run = _run(status="active")
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=run))

    result = asyncio.run(service.activate_campaign_run(db, user_id="user-1", run_id="run-1"))

    assert result is run
    assert db.committed == 0


@pytest.mark.parametrize("status", ["setup", "archived", "finished"])
def test_activate_campaign_run_raises_invalid_run_status_otherwise(status):
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=_run(status=status)))

    with pytest.raises(InvalidRunStatusError):
        asyncio.run(service.activate_campaign_run(db, user_id="user-1", run_id="run-1"))


# --- get_member_character ---------------------------------------------------


def test_get_member_character_returns_the_callers_own_character():
    character = GameObject(
        id="obj-1",
        campaign_run_id="run-1",
        kind="creature",
        instance_key="pc:member-1:1",
        member_id="member-1",
        name="Hero",
    )
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=character))

    result = asyncio.run(service.get_member_character(db, user_id="user-1", run_id="run-1"))

    assert result is character


def test_get_member_character_raises_campaign_run_not_found_for_a_foreign_or_unknown_run():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(service.get_member_character(db, user_id="user-1", run_id="run-1"))


def test_get_member_character_raises_character_not_found_when_the_member_has_none():
    db = FakeSession(FakeResult(scalar=_member()), FakeResult(scalar=None))

    with pytest.raises(CharacterNotFoundError):
        asyncio.run(service.get_member_character(db, user_id="user-1", run_id="run-1"))
