"""Unmocked tests over the real, shipped `backend/content/` tree.

These never monkeypatch `service.CONTENT_ROOT` and never write into
`backend/content/`. They read the actual `greenhollow/v1` campaign and prove
it loads through the real service surface, carrying the addressable exits
(`Exit.id`/`Exit.kind`), the ending exit on `lair-hollow`, and the
item-backed seed inventory landed by sprint 005/01 (`brief.md` AC4), on top
of the standing regression checks carried over from the earlier
object-template rework (criterion numbers `_c26`.. refer to `step-1.4.md`
§10, "The shipped tree", 26-31).
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from app.modules.content import service
from app.modules.content.commands import content_app

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

CREATURE_IDS = ["mira", "goblin", "goblin-boss"]
ITEM_IDS = [
    "shepherds-knife",
    "bent-horseshoe",
    "notched-cleaver",
    "stolen-fleece",
    "wooden-shield",
    "hooded-lantern",
    "coil-of-twine",
    "rations",
]
FIXTURE_IDS = ["thorn-screen", "wool-sack"]

SEED_INVENTORY = ["shepherds-knife", "wooden-shield", "hooded-lantern", "coil-of-twine", "rations"]

runner = CliRunner()


def _version_dir() -> Path:
    return service.CONTENT_ROOT / "campaigns" / CAMPAIGN_ID / VERSION


# --- 26: definitions/ is gone, exactly two entries remain --------------------


def test_definitions_directory_does_not_exist_c26():
    assert not (_version_dir() / "definitions").exists()


def test_version_directory_holds_exactly_campaign_json_and_adventures_c26():
    entries = {p.name for p in _version_dir().iterdir()}
    assert entries == {"campaign.json", "adventures"}


# --- object_templates has exactly thirteen entries, in the pinned order -----
# (supersedes the old nine-entry pin, step-1.4.md's c27: sprint 005/01 added
# four item templates)


def test_object_templates_has_thirteen_entries_in_pinned_order():
    campaign_data = json.loads((_version_dir() / "campaign.json").read_text())
    ids_and_kinds = [(t["id"], t["kind"]) for t in campaign_data["object_templates"]]

    assert ids_and_kinds == [
        ("mira", "creature"),
        ("goblin", "creature"),
        ("goblin-boss", "creature"),
        ("shepherds-knife", "item"),
        ("bent-horseshoe", "item"),
        ("notched-cleaver", "item"),
        ("stolen-fleece", "item"),
        ("wooden-shield", "item"),
        ("hooded-lantern", "item"),
        ("coil-of-twine", "item"),
        ("rations", "item"),
        ("thorn-screen", "fixture"),
        ("wool-sack", "fixture"),
    ]


def test_new_item_templates_have_the_same_shape_as_the_existing_ones():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    templates = loaded.object_templates

    for item_id in ["wooden-shield", "hooded-lantern", "coil-of-twine", "rations"]:
        template = templates[item_id]
        assert template.kind == "item"
        assert template.attacks == []
        assert template.name
        assert template.description


# --- 27a: completeness -- no mechanism ships unexercised ----------------------


def test_loaded_campaign_exercises_every_pinned_mechanism_c27a():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    templates = loaded.object_templates
    scenes = loaded.scenes

    assert set(templates.keys()) == set(CREATURE_IDS + ITEM_IDS + FIXTURE_IDS)

    # a creature placement that carries
    village_green = scenes["village-green"]
    mira_placement = next(p for p in village_green.placements if p.template == "mira")
    assert mira_placement.carries == [
        type(mira_placement.carries[0])(template="shepherds-knife", count=1)
    ]

    lair_hollow = scenes["lair-hollow"]
    boss_placement = next(p for p in lair_hollow.placements if p.template == "goblin-boss")
    assert [c.template for c in boss_placement.carries] == ["notched-cleaver"]

    # a fixture placement that carries, with count > 1
    sack_placement = next(p for p in lair_hollow.placements if p.template == "wool-sack")
    assert [(c.template, c.count) for c in sack_placement.carries] == [("stolen-fleece", 2)]

    # a bare item placement, no carrier, carries omitted (defaults to [])
    horseshoe_placement = next(
        p for p in village_green.placements if p.template == "bent-horseshoe"
    )
    assert horseshoe_placement.carries == []

    # a placement with count > 1
    lair_maw = scenes["lair-maw"]
    goblin_placement = next(p for p in lair_maw.placements if p.template == "goblin")
    assert goblin_placement.count == 3

    # a scene with no placements
    assert scenes["thornway"].placements == []

    # item templates: non-empty attacks and attacks == []
    assert templates["shepherds-knife"].attacks != []
    assert templates["notched-cleaver"].attacks != []
    assert templates["bent-horseshoe"].attacks == []
    assert templates["stolen-fleece"].attacks == []

    # each fixture: first check bypassed_by == [], second lists only items
    for fixture_id in FIXTURE_IDS:
        checks = templates[fixture_id].checks
        assert len(checks) == 2
        assert checks[0].bypassed_by == []
        assert checks[1].bypassed_by
        for item_id in checks[1].bypassed_by:
            assert templates[item_id].kind == "item"

    # both bypass chains are playable: at least one listed item is placed or
    # carried somewhere in the tree. shepherds-knife also ships in the seed
    # inventory now (sprint 005/01), but it is still carried by Mira here, so
    # this reasoning over scene placements/carries is unaffected.
    all_carried_or_placed_item_ids = {
        p.template
        for scene in scenes.values()
        for p in scene.placements
        if templates[p.template].kind == "item"
    } | {c.template for scene in scenes.values() for p in scene.placements for c in p.carries}
    assert "shepherds-knife" in all_carried_or_placed_item_ids
    assert "notched-cleaver" in all_carried_or_placed_item_ids


# --- 27b: both bypassed_by cardinalities ship ---------------------------------


def test_bypassed_by_cardinalities_c27b():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    templates = loaded.object_templates

    thorn_screen_checks = templates["thorn-screen"].checks
    assert thorn_screen_checks[1].bypassed_by == ["shepherds-knife", "notched-cleaver"]

    wool_sack_checks = templates["wool-sack"].checks
    assert wool_sack_checks[1].bypassed_by == ["notched-cleaver"]

    assert thorn_screen_checks[0].bypassed_by == []
    assert wool_sack_checks[0].bypassed_by == []


def test_bypassed_by_key_absent_from_first_checks_in_shipped_json_c27b():
    campaign_data = json.loads((_version_dir() / "campaign.json").read_text())
    fixtures_by_id = {
        t["id"]: t for t in campaign_data["object_templates"] if t["kind"] == "fixture"
    }

    for fixture_id in FIXTURE_IDS:
        assert "bypassed_by" not in fixtures_by_id[fixture_id]["checks"][0]


# --- 29: migration fidelity -- no old keys survive -----------------------------


def test_no_old_keys_survive_under_the_greenhollow_tree_c29():
    for path in _version_dir().rglob("*.json"):
        text = path.read_text()
        assert '"creatures"' not in text, path
        assert '"definition"' not in text, path


# --- 30: the four scenes' placements, exactly ----------------------------------


def test_scene_placements_match_the_pinned_shape_c30():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    scenes = loaded.scenes

    village_green = scenes["village-green"]
    assert [(p.template, p.count) for p in village_green.placements] == [
        ("mira", 1),
        ("bent-horseshoe", 1),
    ]

    assert scenes["thornway"].placements == []

    lair_maw = scenes["lair-maw"]
    assert [(p.template, p.count) for p in lair_maw.placements] == [
        ("goblin", 3),
        ("thorn-screen", 1),
    ]

    lair_hollow = scenes["lair-hollow"]
    assert [(p.template, p.count) for p in lair_hollow.placements] == [
        ("goblin-boss", 1),
        ("goblin", 1),
        ("wool-sack", 1),
    ]

    # scene ids and order, per the adventure's own scene list, unchanged
    adventure = next(iter(loaded.adventures.values()))
    assert [s.id for s in adventure.scenes] == [
        "village-green",
        "thornway",
        "lair-maw",
        "lair-hollow",
    ]

    # sprint 005/01: lair-hollow no longer ends the adventure with an empty
    # exits list -- it carries exactly one exit, the adventure_end exit
    assert [e.id for e in lair_hollow.exits] == ["leave-the-hollow"]
    assert lair_hollow.exits[0].kind == "adventure_end"


# --- 31: step-1.3 criteria survive the rename ----------------------------------


def test_step_1_3_structural_criteria_survive_the_rename_c31():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)

    assert service.list_campaign_ids() == [CAMPAIGN_ID]
    assert service.list_versions(CAMPAIGN_ID) == [VERSION]
    assert len(loaded.adventures) == 1
    assert len(loaded.scenes) == 4

    adventure = next(iter(loaded.adventures.values()))
    assert adventure.entry_scene != "lair-hollow"  # terminal scene isn't the entry scene
    # sprint 005/01: lair-hollow ends the adventure through an adventure_end
    # exit rather than an empty exits list
    assert [e.id for e in loaded.scenes["lair-hollow"].exits] == ["leave-the-hollow"]
    assert loaded.scenes["lair-hollow"].exits[0].kind == "adventure_end"

    # goblin placed in two scenes
    scenes_with_goblin = [
        scene_id
        for scene_id, scene in loaded.scenes.items()
        if any(p.template == "goblin" for p in scene.placements)
    ]
    assert len(scenes_with_goblin) == 2

    # mira has attacks == [], at least one creature has a non-empty attacks list
    creature_templates = [t for t in loaded.object_templates.values() if t.kind == "creature"]
    assert loaded.object_templates["mira"].stat_block.attacks == []
    assert any(t.stat_block.attacks for t in creature_templates)

    # two hidden entries across two scenes
    scenes_with_hidden = [scene for scene in loaded.scenes.values() if scene.hidden]
    assert len(scenes_with_hidden) >= 2

    # one exit with a condition, one without
    all_exits = [exit_ for scene in loaded.scenes.values() for exit_ in scene.exits]
    assert any(exit_.condition is not None for exit_ in all_exits)
    assert any(exit_.condition is None for exit_ in all_exits)

    # a placement with count > 1
    all_placements = [p for scene in loaded.scenes.values() for p in scene.placements]
    assert any(p.count > 1 for p in all_placements)

    # a consequences entry naming the villain verbatim
    all_consequences = " ".join(c for scene in loaded.scenes.values() for c in scene.consequences)
    assert "Grettle" in all_consequences


# --- AC4: exit ids and the ending exit ---------------------------------------


def test_exits_carry_the_pinned_ids():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    scenes = loaded.scenes

    assert [e.id for e in scenes["village-green"].exits] == ["to-thornway"]
    assert [e.id for e in scenes["thornway"].exits] == ["to-lair-maw"]
    assert [e.id for e in scenes["lair-maw"].exits] == ["to-lair-hollow"]
    assert [e.id for e in scenes["lair-hollow"].exits] == ["leave-the-hollow"]


def test_lair_hollow_carries_the_adventure_end_exit():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    ending_exit = loaded.scenes["lair-hollow"].exits[0]

    assert ending_exit.kind == "adventure_end"
    assert ending_exit.to is None
    assert ending_exit.condition is None
    assert ending_exit.description


def test_scene_exits_still_target_a_known_scene_and_carry_to():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    scenes = loaded.scenes

    assert scenes["village-green"].exits[0].kind == "scene"
    assert scenes["village-green"].exits[0].to == "thornway"
    assert scenes["thornway"].exits[0].to == "lair-maw"
    assert scenes["lair-maw"].exits[0].to == "lair-hollow"


# --- AC4: the seed inventory names item templates ----------------------------


def test_seed_character_inventory_names_the_pinned_item_templates():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)

    assert loaded.campaign.seed_character.inventory == SEED_INVENTORY
    for template_id in loaded.campaign.seed_character.inventory:
        assert loaded.object_templates[template_id].kind == "item"


# --- 32: the CLI still exits 0 on this tree -------------------------------------


def test_content_app_validates_shipped_tree_c32():
    result = runner.invoke(content_app, [])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"{CAMPAIGN_ID}/{VERSION}: ok"
    assert result.stderr == ""
