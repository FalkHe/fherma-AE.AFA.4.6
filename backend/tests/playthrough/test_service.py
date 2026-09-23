"""WI1: starting, listing and reading a campaign run (AC1-AC3's service
half). Engine-free throughout: `FakeSession` stands in for `AsyncSession`
the way `tests/srd/test_service.py` does -- `execute()` returns queued
results, and `add`/`add_all`/`flush`/`commit`/`rollback` simulate just
enough of SQLAlchemy's unit of work (id defaults, the
`(campaign_run_id, instance_key)` uniqueness constraint) for
`start_campaign_run` to be exercised without a database. Content loading
uses the real shipped `greenhollow/v1` campaign (`content.service` only
touches the filesystem, never a database), so the object-instantiation
tests exercise the real content the acceptance suite (WI4) also uses.

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from datetime import UTC, datetime

import pytest
import structlog.testing
from sqlalchemy.exc import IntegrityError

from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.content.errors import ContentInvalidError, ContentNotFoundError
from app.modules.content.schemas import (
    Abilities,
    Adventure,
    Campaign,
    Carried,
    CreatureTemplate,
    ItemTemplate,
    LoadedCampaign,
    Placement,
    Scene,
    SeedCharacter,
    StatBlock,
)
from app.modules.playthrough import service
from app.modules.playthrough.errors import (
    CampaignNotFoundError,
    CampaignRunExistsError,
    CampaignRunNotFoundError,
)
from app.modules.playthrough.models import AdventureRun, CampaignRun, CampaignRunMember, GameObject

GREENHOLLOW_KEYS = {
    "goblins-of-greenhollow:village-green:mira:1",
    "goblins-of-greenhollow:village-green:mira:1/shepherds-knife:1",
    "goblins-of-greenhollow:village-green:bent-horseshoe:1",
    "goblins-of-greenhollow:lair-maw:goblin:1",
    "goblins-of-greenhollow:lair-maw:goblin:2",
    "goblins-of-greenhollow:lair-maw:goblin:3",
    "goblins-of-greenhollow:lair-maw:thorn-screen:1",
    "goblins-of-greenhollow:lair-hollow:goblin-boss:1",
    "goblins-of-greenhollow:lair-hollow:goblin-boss:1/notched-cleaver:1",
    "goblins-of-greenhollow:lair-hollow:goblin:1",
    "goblins-of-greenhollow:lair-hollow:wool-sack:1",
    "goblins-of-greenhollow:lair-hollow:wool-sack:1/stolen-fleece:1",
    "goblins-of-greenhollow:lair-hollow:wool-sack:1/stolen-fleece:2",
}


def _load_greenhollow() -> LoadedCampaign:
    return content_service.load_campaign("greenhollow", "v1")


def _make_campaign_run(**overrides) -> CampaignRun:
    fields = dict(
        id=generate_id(),
        campaign_id="greenhollow",
        content_version="v1",
        status="setup",
        created_at=datetime.now(UTC),
    )
    fields.update(overrides)
    return CampaignRun(**fields)


class FakeResult:
    """Stands in for the object `AsyncSession.execute()` returns."""

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
    """Engine-free stand-in for `AsyncSession`.

    `execute()` returns the queued results in order. `flush()` assigns an
    id (via `id_generator`, defaulting to the real `generate_id`) to any
    added row that does not already have one -- the way a column's
    Python-side default is populated during a real flush -- and enforces
    the `(campaign_run_id, instance_key)` uniqueness constraint the way
    Postgres would, raising `IntegrityError` on a clash. State persists
    across separate calls made against the same instance, so reusing one
    session for two `start_campaign_run()` calls simulates a repeat start
    without needing a real database.
    """

    def __init__(self, *results, id_generator=generate_id):
        self._results = list(results)
        self._id_generator = id_generator
        self.added: list[object] = []
        self.persisted: list[object] = []
        self.committed = 0
        self.rolled_back = 0
        self._object_keys: set[tuple[str, str]] = set()

    async def execute(self, _stmt):
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
            if isinstance(obj, GameObject):
                key = (obj.campaign_run_id, obj.instance_key)
                if key in self._object_keys:
                    raise IntegrityError(
                        "INSERT INTO objects", {}, Exception("uq_objects_campaign_run_id")
                    )
                self._object_keys.add(key)
        self.persisted.extend(pending)

    async def commit(self):
        await self.flush()
        self.committed += 1

    async def rollback(self):
        self.added = []
        self.rolled_back += 1

    async def refresh(self, _obj):
        return None


# --- _build_run_objects / _build_object -------------------------------------


def test_build_run_objects_writes_exactly_the_greenhollow_key_set():
    loaded = _load_greenhollow()

    placements, carried = service._build_run_objects(loaded, campaign_run_id="run-1")

    keys = {row.instance_key for row in placements} | {row.instance_key for row in carried}
    assert keys == GREENHOLLOW_KEYS
    assert len(placements) + len(carried) == 13


def test_build_run_objects_leaves_every_row_unpositioned():
    loaded = _load_greenhollow()

    placements, carried = service._build_run_objects(loaded, campaign_run_id="run-1")

    for row in placements + carried:
        assert row.campaign_run_id == "run-1"
        assert row.adventure_run_id is None
        assert row.scene_id is None
        assert row.member_id is None


def test_build_run_objects_copies_name_and_provenance_from_the_template():
    loaded = _load_greenhollow()

    placements, _carried = service._build_run_objects(loaded, campaign_run_id="run-1")

    mira = next(row for row in placements if row.template_id == "mira")
    assert mira.name == "Mira"
    assert mira.source_adventure_id == "goblins-of-greenhollow"
    assert mira.source_scene_id == "village-green"


def test_build_run_objects_sets_creature_stats_from_the_stat_block():
    loaded = _load_greenhollow()

    placements, _carried = service._build_run_objects(loaded, campaign_run_id="run-1")

    mira = next(row for row in placements if row.template_id == "mira")
    assert mira.kind == "creature"
    assert mira.max_hp == 8
    assert mira.current_hp == 8
    assert mira.armour_class == 10
    assert mira.is_alive is True


def test_build_run_objects_leaves_stats_null_on_item_and_fixture_rows():
    loaded = _load_greenhollow()

    placements, carried = service._build_run_objects(loaded, campaign_run_id="run-1")

    horseshoe = next(row for row in placements if row.template_id == "bent-horseshoe")
    knife = next(row for row in carried if row.template_id == "shepherds-knife")
    for row in (horseshoe, knife):
        assert row.max_hp is None
        assert row.current_hp is None
        assert row.armour_class is None
        assert row.is_alive is None


def test_build_run_objects_links_a_carried_row_to_its_placement_instance():
    loaded = _load_greenhollow()

    placements, carried = service._build_run_objects(loaded, campaign_run_id="run-1")

    mira = next(row for row in placements if row.template_id == "mira")
    knife = next(row for row in carried if row.template_id == "shepherds-knife")
    assert knife.owner_object_id == mira.id
    assert mira.owner_object_id is None


def test_build_run_objects_gives_each_placement_instance_its_own_carried_child():
    """A placement with `count: 3` that carries something yields three
    carried rows, one per placement instance -- no shipped content does
    this yet, so it is exercised with a hand-built campaign here."""
    template_creature = CreatureTemplate(
        id="bandit",
        kind="creature",
        name="Bandit",
        description="d",
        disposition="d",
        stat_block=StatBlock(
            max_hp=5,
            armour_class=12,
            abilities=Abilities(
                strength=10, dexterity=10, constitution=10, intelligence=10, wisdom=10, charisma=10
            ),
        ),
    )
    template_dagger = ItemTemplate(id="dagger", kind="item", name="Dagger", description="d")
    scene = Scene(
        id="camp",
        title="Camp",
        truth=["t"],
        placements=[Placement(template="bandit", count=3, carries=[Carried(template="dagger")])],
    )
    adventure = Adventure(id="raid", title="Raid", intro="i", entry_scene="camp", scenes=[scene])
    campaign = Campaign(
        id="test-campaign",
        title="Test",
        summary="s",
        adventures=["raid"],
        seed_character=SeedCharacter(
            name="n",
            race="r",
            character_class="c",
            background="b",
            appearance="a",
            abilities=Abilities(
                strength=10, dexterity=10, constitution=10, intelligence=10, wisdom=10, charisma=10
            ),
            max_hp=10,
            armour_class=10,
        ),
        object_templates=[template_creature, template_dagger],
    )
    loaded = LoadedCampaign(
        campaign=campaign,
        version="v1",
        adventures={"raid": adventure},
        scenes={"camp": scene},
        object_templates={"bandit": template_creature, "dagger": template_dagger},
    )

    placements, carried = service._build_run_objects(loaded, campaign_run_id="run-1")

    assert len(placements) == 3
    assert len(carried) == 3
    assert {row.owner_object_id for row in carried} == {row.id for row in placements}
    assert {row.instance_key for row in carried} == {
        "raid:camp:bandit:1/dagger:1",
        "raid:camp:bandit:2/dagger:1",
        "raid:camp:bandit:3/dagger:1",
    }


# --- _require_member ----------------------------------------------------


def test_require_member_returns_the_member_row_when_one_exists():
    member = CampaignRunMember(campaign_run_id="run-1", user_id="user-1", role="owner")
    db = FakeSession(FakeResult(scalar=member))

    result = asyncio.run(service._require_member(db, run_id="run-1", user_id="user-1"))

    assert result is member


def test_require_member_raises_not_found_when_no_row_matches():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(service._require_member(db, run_id="run-1", user_id="user-1"))


# --- start_campaign_run ---------------------------------------------------


def test_start_campaign_run_pins_the_latest_content_version():
    db = FakeSession()

    run = asyncio.run(service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow"))

    assert run.campaign_id == "greenhollow"
    assert run.content_version == "v1"


def test_start_campaign_run_creates_the_owner_membership():
    db = FakeSession()

    run = asyncio.run(service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow"))

    members = [obj for obj in db.persisted if isinstance(obj, CampaignRunMember)]
    assert len(members) == 1
    assert members[0].campaign_run_id == run.id
    assert members[0].user_id == "user-1"
    assert members[0].role == "owner"


def test_start_campaign_run_writes_every_declared_object_unplaced():
    db = FakeSession()

    run = asyncio.run(service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow"))

    objects = [obj for obj in db.persisted if isinstance(obj, GameObject)]
    assert {obj.instance_key for obj in objects} == GREENHOLLOW_KEYS
    assert all(obj.campaign_run_id == run.id for obj in objects)
    assert all(obj.adventure_run_id is None and obj.scene_id is None for obj in objects)


def test_start_campaign_run_commits_once_and_appends_no_event():
    db = FakeSession()

    asyncio.run(service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow"))

    assert db.committed == 1
    kinds = {type(obj).__name__ for obj in db.persisted}
    assert kinds == {"CampaignRun", "CampaignRunMember", "GameObject"}


def test_start_campaign_run_raises_not_found_for_an_unknown_campaign():
    db = FakeSession()

    with pytest.raises(CampaignNotFoundError) as excinfo:
        asyncio.run(
            service.start_campaign_run(db, user_id="user-1", campaign_id="no-such-campaign")
        )

    assert excinfo.value.__cause__ is not None


def test_starting_the_same_campaign_twice_yields_two_distinct_runs():
    """003 explicitly allows repeat runs of the same campaign: a run's id
    is minted fresh (`core.ids.generate_id`, the same helper every module
    uses), never derived from `(user_id, campaign_id)`, so a second start
    is a second, independent playthrough -- not a conflict."""
    db = FakeSession()

    first = asyncio.run(service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow"))
    second = asyncio.run(
        service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow")
    )

    assert first.id != second.id
    objects = [obj for obj in db.persisted if isinstance(obj, GameObject)]
    assert {obj.instance_key for obj in objects if obj.campaign_run_id == first.id} == (
        GREENHOLLOW_KEYS
    )
    assert {obj.instance_key for obj in objects if obj.campaign_run_id == second.id} == (
        GREENHOLLOW_KEYS
    )


def test_a_duplicate_instance_key_within_one_run_is_refused_by_the_key_not_a_pre_check():
    """`(campaign_run_id, instance_key)` is unique *within one run* (I5):
    it guards a single run's world being instantiated exactly once, not
    against a second run of the same campaign. There is no pre-check --
    if it were ever violated, the resulting `IntegrityError` is what
    `CampaignRunExistsError` translates. Forcing the same run id twice
    (via a fixed `id_generator`) is the only way to observe that
    translation without a real database, since a fresh id never
    collides."""
    db = FakeSession(id_generator=lambda: "fixed-run-id")

    asyncio.run(service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow"))

    with pytest.raises(CampaignRunExistsError) as excinfo:
        asyncio.run(service.start_campaign_run(db, user_id="user-1", campaign_id="greenhollow"))

    assert isinstance(excinfo.value.__cause__, IntegrityError)
    assert db.rolled_back == 1


# --- list_campaign_runs / get_campaign_run --------------------------------


def test_list_campaign_runs_returns_the_queried_rows_in_order():
    newest = CampaignRun(id="run-2", campaign_id="greenhollow", content_version="v1")
    oldest = CampaignRun(id="run-1", campaign_id="greenhollow", content_version="v1")
    db = FakeSession(FakeResult(scalars=[newest, oldest]))

    runs = asyncio.run(service.list_campaign_runs(db, user_id="user-1"))

    assert runs == [newest, oldest]


def test_get_campaign_run_returns_the_run_once_membership_is_confirmed():
    member = CampaignRunMember(campaign_run_id="run-1", user_id="user-1", role="owner")
    run = CampaignRun(id="run-1", campaign_id="greenhollow", content_version="v1")
    db = FakeSession(FakeResult(scalar=member), FakeResult(scalar=run))

    result = asyncio.run(service.get_campaign_run(db, user_id="user-1", run_id="run-1"))

    assert result is run


def test_get_campaign_run_raises_not_found_for_a_foreign_run():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(service.get_campaign_run(db, user_id="user-1", run_id="someone-elses-run"))


# --- list_run_summaries / _load_pinned -------------------------------------


def test_load_pinned_returns_the_loaded_campaign_for_a_healthy_run():
    run = CampaignRun(id="run-1", campaign_id="greenhollow", content_version="v1")

    loaded = service._load_pinned(run)

    assert loaded.campaign.id == "greenhollow"


def test_load_pinned_returns_none_and_logs_a_warning_on_a_content_error(monkeypatch):
    run = CampaignRun(id="run-1", campaign_id="greenhollow", content_version="v1")

    def fake_load_campaign(campaign_id, version):
        raise ContentNotFoundError("greenhollow/v1")

    monkeypatch.setattr(content_service, "load_campaign", fake_load_campaign)

    with structlog.testing.capture_logs() as logs:
        loaded = service._load_pinned(run)

    assert loaded is None
    warnings = [entry for entry in logs if entry["log_level"] == "warning"]
    assert len(warnings) == 1
    assert warnings[0]["event"] == "playthrough_content_unavailable"
    assert warnings[0]["run_id"] == "run-1"


def test_list_run_summaries_orders_and_includes_archived_runs_exactly_as_queried():
    newest = _make_campaign_run(id="run-2", status="archived")
    oldest = _make_campaign_run(id="run-1", status="setup")
    db = FakeSession(
        FakeResult(scalars=[newest, oldest]),
        FakeResult(scalars=[]),
        FakeResult(scalars=[]),
    )

    summaries = asyncio.run(service.list_run_summaries(db, user_id="user-1"))

    assert [summary.id for summary in summaries] == ["run-2", "run-1"]
    assert summaries[0].status == "archived"


def test_list_run_summaries_takes_the_completed_count_from_the_adventure_run_rows():
    run = _make_campaign_run(id="run-1")
    other = _make_campaign_run(id="run-2")
    db = FakeSession(
        FakeResult(scalars=[run, other]),
        FakeResult(scalars=[("run-1", 2)]),
        FakeResult(scalars=[("run-1", 1), ("run-2", 4)]),
    )

    summaries = asyncio.run(service.list_run_summaries(db, user_id="user-1"))

    by_id = {summary.id: summary for summary in summaries}
    assert by_id["run-1"].adventures_completed == 2
    assert by_id["run-1"].player_count == 1
    assert by_id["run-2"].adventures_completed == 0
    assert by_id["run-2"].player_count == 4


def test_list_run_summaries_flags_unavailable_content_without_raising_and_leaves_a_sibling_intact(
    monkeypatch,
):
    healthy = _make_campaign_run(id="run-1")
    missing = _make_campaign_run(id="run-2", campaign_id="ghost-town")
    broken = _make_campaign_run(id="run-3", campaign_id="ruined-keep")
    db = FakeSession(
        FakeResult(scalars=[healthy, missing, broken]),
        FakeResult(scalars=[]),
        FakeResult(scalars=[]),
    )

    real_load_campaign = content_service.load_campaign

    def fake_load_campaign(campaign_id, version):
        if campaign_id == "ghost-town":
            raise ContentNotFoundError("ghost-town/v1")
        if campaign_id == "ruined-keep":
            raise ContentInvalidError("ruined-keep", "v1", ["broken"])
        return real_load_campaign(campaign_id, version)

    monkeypatch.setattr(content_service, "load_campaign", fake_load_campaign)

    summaries = asyncio.run(service.list_run_summaries(db, user_id="user-1"))

    by_id = {summary.id: summary for summary in summaries}
    for run_id in ("run-2", "run-3"):
        summary = by_id[run_id]
        assert summary.unavailable is True
        assert summary.campaign_title is None
        assert summary.campaign_summary is None
        assert summary.adventures_total is None

    sibling = by_id["run-1"]
    assert sibling.unavailable is False
    assert sibling.campaign_title == "Greenhollow"
    assert sibling.adventures_total == 1


def test_list_run_summaries_loads_pinned_content_only_once_for_two_runs_of_one_campaign(
    monkeypatch,
):
    first = _make_campaign_run(id="run-1")
    second = _make_campaign_run(id="run-2")
    db = FakeSession(
        FakeResult(scalars=[first, second]),
        FakeResult(scalars=[]),
        FakeResult(scalars=[]),
    )

    calls = []
    real_load_campaign = content_service.load_campaign

    def counting_load_campaign(campaign_id, version):
        calls.append((campaign_id, version))
        return real_load_campaign(campaign_id, version)

    monkeypatch.setattr(content_service, "load_campaign", counting_load_campaign)

    asyncio.run(service.list_run_summaries(db, user_id="user-1"))

    assert calls == [("greenhollow", "v1")]


def test_list_run_summaries_makes_no_write():
    run = _make_campaign_run(id="run-1")
    db = FakeSession(
        FakeResult(scalars=[run]),
        FakeResult(scalars=[]),
        FakeResult(scalars=[]),
    )

    asyncio.run(service.list_run_summaries(db, user_id="user-1"))

    assert db.committed == 0
    assert db.added == []


# --- get_run_overview / _excerpt (WI2) --------------------------------------


def test_excerpt_keeps_a_short_text_verbatim():
    text = "Smoke rises over the hedgerows."

    assert service._excerpt(text) == text


def test_excerpt_clips_a_long_text_at_a_word_boundary_and_appends_an_ellipsis():
    text = "A" * 50 + " " + "B" * 200

    excerpt = service._excerpt(text, limit=200)

    assert excerpt == "A" * 50 + "…"
    assert len(text[:200]) == 200  # sanity: the cut really does land mid-word


def _member_row(*, member_id="member-1", run_id="run-1", user_id="user-1", role="owner"):
    return CampaignRunMember(id=member_id, campaign_run_id=run_id, user_id=user_id, role=role)


def _character_object(**overrides) -> GameObject:
    fields = {
        "id": "character-1",
        "campaign_run_id": "run-1",
        "member_id": "member-1",
        "kind": "creature",
        "instance_key": "pc:member-1:1",
        "name": "Rosalind Thorn",
        "current_hp": 9,
        "max_hp": 9,
        "armour_class": 14,
        "is_alive": True,
        "state": {
            "abilities": {
                "strength": 8,
                "dexterity": 16,
                "constitution": 14,
                "intelligence": 12,
                "wisdom": 10,
                "charisma": 13,
            },
            "race": "Halfling",
            "character_class": "Rogue",
            "background": "Raised in the kitchens of a river inn.",
            "appearance": "Barely three feet of him, all elbows and grin.",
        },
    }
    fields.update(overrides)
    return GameObject(**fields)


def test_get_run_overview_members_carry_username_and_role():
    run = _make_campaign_run(id="run-1")
    member = _member_row()
    row = (_member_row(), "aragorn", None)
    db = FakeSession(
        FakeResult(scalar=member),
        FakeResult(scalar=run),
        FakeResult(scalars=[row]),
        FakeResult(scalars=[]),
    )

    overview = asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))

    assert len(overview.members) == 1
    assert overview.members[0].username == "aragorn"
    assert overview.members[0].role == "owner"


def test_get_run_overview_ready_is_false_with_no_character():
    run = _make_campaign_run(id="run-1")
    member = _member_row()
    row = (_member_row(), "aragorn", None)
    db = FakeSession(
        FakeResult(scalar=member),
        FakeResult(scalar=run),
        FakeResult(scalars=[row]),
        FakeResult(scalars=[]),
    )

    overview = asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))

    assert overview.members[0].ready is False
    assert overview.members[0].character is None


def test_get_run_overview_ready_is_true_once_the_member_owns_a_character():
    run = _make_campaign_run(id="run-1")
    member = _member_row()
    row = (_member_row(), "frodo", _character_object())
    db = FakeSession(
        FakeResult(scalar=member),
        FakeResult(scalar=run),
        FakeResult(scalars=[row]),
        FakeResult(scalars=[]),
    )

    overview = asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))

    assert overview.members[0].ready is True
    character = overview.members[0].character
    assert character.name == "Rosalind Thorn"
    assert character.race == "Halfling"
    assert character.character_class == "Rogue"
    assert character.level == 1
    assert character.appearance == "Barely three feet of him, all elbows and grin."


def test_get_run_overview_member_query_joins_the_character_by_member_id_and_kind():
    """An NPC's `objects` row has `member_id` NULL (research: only a
    member's own character carries `member_id`), so it can never satisfy
    `member_id == member.id` -- the join predicate itself, not a Python
    filter, is what keeps a non-player creature from ever supplying a
    `character_name` and flipping a member `ready`. Asserted here by
    inspecting the compiled statement, the way
    `test_service_enter_adventure.py`'s `_compiled` helper already does in
    this suite."""
    run = _make_campaign_run(id="run-1")
    member = _member_row()
    captured: list[object] = []

    class CapturingSession(FakeSession):
        async def execute(self, stmt):
            captured.append(stmt)
            return await super().execute(stmt)

    db = CapturingSession(
        FakeResult(scalar=member),
        FakeResult(scalar=run),
        FakeResult(scalars=[]),
        FakeResult(scalars=[]),
    )

    asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))

    member_stmt = captured[2]
    compiled = str(member_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "objects.member_id = campaign_run_members.id" in compiled
    assert "objects.kind = 'creature'" in compiled


def _synthetic_three_adventure_campaign() -> LoadedCampaign:
    def _adventure(adventure_id: str) -> Adventure:
        scene = Scene(id=f"{adventure_id}-scene", title="Scene", truth=["t"])
        return Adventure(
            id=adventure_id,
            title=adventure_id.replace("-", " ").title(),
            intro=f"Intro for {adventure_id}.",
            entry_scene=scene.id,
            scenes=[scene],
        )

    adventures = {aid: _adventure(aid) for aid in ("first-light", "second-dusk", "third-dawn")}
    campaign = Campaign(
        id="synthetic-campaign",
        title="Synthetic",
        summary="s",
        adventures=list(adventures.keys()),
        seed_character=SeedCharacter(
            name="n",
            race="r",
            character_class="c",
            background="b",
            appearance="a",
            abilities=Abilities(
                strength=10, dexterity=10, constitution=10, intelligence=10, wisdom=10, charisma=10
            ),
            max_hp=10,
            armour_class=10,
        ),
        object_templates=[
            CreatureTemplate(
                id="npc",
                kind="creature",
                name="Npc",
                description="d",
                disposition="d",
                stat_block=StatBlock(
                    max_hp=5,
                    armour_class=10,
                    abilities=Abilities(
                        strength=10,
                        dexterity=10,
                        constitution=10,
                        intelligence=10,
                        wisdom=10,
                        charisma=10,
                    ),
                ),
            )
        ],
    )
    return LoadedCampaign(
        campaign=campaign,
        version="v1",
        adventures=adventures,
        scenes={
            a.entry_scene: Scene(id=a.entry_scene, title="Scene", truth=["t"])
            for a in adventures.values()
        },
        object_templates={"npc": campaign.object_templates[0]},
    )


def test_get_run_overview_adventures_are_in_campaign_order_with_all_three_statuses(monkeypatch):
    run = _make_campaign_run(id="run-1", campaign_id="synthetic-campaign")
    member = _member_row()

    def fake_load_campaign(campaign_id, version):
        return _synthetic_three_adventure_campaign()

    monkeypatch.setattr(content_service, "load_campaign", fake_load_campaign)

    completed = AdventureRun(
        campaign_run_id="run-1", adventure_id="first-light", status="completed"
    )
    active = AdventureRun(campaign_run_id="run-1", adventure_id="second-dusk", status="active")
    db = FakeSession(
        FakeResult(scalar=member),
        FakeResult(scalar=run),
        FakeResult(scalars=[]),
        FakeResult(scalars=[completed, active]),
    )

    overview = asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))

    assert [a.id for a in overview.adventures] == ["first-light", "second-dusk", "third-dawn"]
    assert [a.status for a in overview.adventures] == ["done", "active", "unplayed"]


def test_get_run_overview_unavailable_run_answers_null_copy_and_no_adventures(monkeypatch):
    run = _make_campaign_run(id="run-1", campaign_id="ghost-town")
    member = _member_row()

    def fake_load_campaign(campaign_id, version):
        raise ContentNotFoundError("ghost-town/v1")

    monkeypatch.setattr(content_service, "load_campaign", fake_load_campaign)

    db = FakeSession(
        FakeResult(scalar=member),
        FakeResult(scalar=run),
        FakeResult(scalars=[]),
        FakeResult(scalars=[]),
    )

    overview = asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))

    assert overview.unavailable is True
    assert overview.campaign_title is None
    assert overview.campaign_summary is None
    assert overview.adventures == []


def test_get_run_overview_raises_not_found_for_a_foreign_or_unknown_run():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))


def test_get_run_overview_makes_no_write():
    run = _make_campaign_run(id="run-1")
    member = _member_row()
    db = FakeSession(
        FakeResult(scalar=member),
        FakeResult(scalar=run),
        FakeResult(scalars=[]),
        FakeResult(scalars=[]),
    )

    asyncio.run(service.get_run_overview(db, user_id="user-1", run_id="run-1"))

    assert db.committed == 0
    assert db.added == []
