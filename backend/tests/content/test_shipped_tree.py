"""Unmocked tests over the real, shipped `backend/content/` tree.

These never monkeypatch `service.CONTENT_ROOT` and never write into
`backend/content/`. They read the actual `greenhollow/v1` campaign and prove
it loads through the real service surface, carrying the addressable exits
(`Exit.id`/`Exit.kind`), the ending exit on `lair-hollow`, and the
item-backed seed inventory landed by sprint 005/01 (`brief.md` AC4).
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


# --- object_templates has exactly thirteen entries, in the pinned order -----


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


# --- every template is used, and the whole tree still validates -------------


def test_loaded_campaign_still_exercises_every_pinned_mechanism():
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    templates = loaded.object_templates

    assert set(templates.keys()) == set(CREATURE_IDS + ITEM_IDS + FIXTURE_IDS)

    # each fixture: first check bypassed_by == [], second lists only items
    for fixture_id in FIXTURE_IDS:
        checks = templates[fixture_id].checks
        assert checks[0].bypassed_by == []
        assert checks[1].bypassed_by
        for item_id in checks[1].bypassed_by:
            assert templates[item_id].kind == "item"


def test_content_app_validates_shipped_tree():
    result = runner.invoke(content_app, [])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"{CAMPAIGN_ID}/{VERSION}: ok"
    assert result.stderr == ""
