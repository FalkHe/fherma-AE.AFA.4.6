"""Fixtures and content-tree builders shared by `tests/content/`.

Mode-A note (step-1.4.md, the object-template rework): this rewrites the
step-1.1/1.3 fixtures for the new two-file layout and the `ObjectTemplate`
union. Every test in this package is expected to fail or error until
backend-dev lands the schema/service rework -- that is correct mode-A
behaviour, not a defect.

**The two-file layout (step-1.4.md §4).** There is no `definitions/`
directory any more: `campaign.json` carries `object_templates[]` and a scene
carries `placements[]`. `build_version_dir` therefore writes only
`campaign.json` and `adventures/<id>.json`.

Nothing here is committed as a fixture corpus: `build_version_dir` writes a
worked example (or a deliberately broken variant of it) into `tmp_path` for
the duration of one test, and `content_root` repoints `service.CONTENT_ROOT`
there via `monkeypatch.setattr` -- never
`from app.modules.content.service import CONTENT_ROOT`, which would rebind
the value and make the monkeypatch silently miss (D10 / shared-knowledge.md
§5.1).

**The worked fixture campaign, `hollow-reach`.** One creature template
(`bog-lurker`), one item template (`rusty-key`) and one fixture template
(`sunken-door`) -- enough to exercise all three `ObjectTemplate` kinds, a
creature placement that carries, a bare item placement, and a
`bypassed_by` chain, without trying to be the Greenhollow worked example
(which is step-1.4.md §5's job and belongs to `test_shipped_tree.py`).
"""

import copy
import json
from pathlib import Path

import pytest

from app.modules.content import service

CAMPAIGN_ID = "hollow-reach"
VERSION = "v1"

ABILITIES: dict = {
    "strength": 9,
    "dexterity": 16,
    "constitution": 12,
    "intelligence": 11,
    "wisdom": 13,
    "charisma": 14,
}

SEED_CHARACTER: dict = {
    "name": "Perrin Ashdown",
    "race": "Halfling",
    "character_class": "Rogue",
    "background": "A river-barge thief who owes the warden a favour and would rather not.",
    "appearance": (
        "Small, weather-browned, with a river-knotted braid and a coat two sizes too large."
    ),
    "abilities": ABILITIES,
    "max_hp": 9,
    "armour_class": 14,
    "inventory": ["rusty-key"],
}

CREATURE_TEMPLATE: dict = {
    "id": "bog-lurker",
    "kind": "creature",
    "name": "Bog Lurker",
    "description": (
        "A flat, mottled thing the length of a man, all mouth and patience, "
        "indistinguishable from silt until it moves."
    ),
    "disposition": (
        "Ambush predator. Attacks anything that enters the water and "
        "retreats under it when badly hurt."
    ),
    "stat_block": {
        "max_hp": 11,
        "armour_class": 13,
        "abilities": ABILITIES,
        "attacks": [{"name": "Bite", "to_hit": 4, "damage": "1d6+2"}],
        "traits": ["Cannot be seen under still water without a deliberate search."],
    },
}

ITEM_TEMPLATE: dict = {
    "id": "rusty-key",
    "kind": "item",
    "name": "Rusty Key",
    "description": "A small iron key, pitted with rust, on a loop of waxed cord.",
    "attacks": [],
}

FIXTURE_TEMPLATE: dict = {
    "id": "sunken-door",
    "kind": "fixture",
    "name": "Sunken Door",
    "description": "A swollen wooden door set into the flooded wall, warped shut by the water.",
    "checks": [
        {
            "action": "Force the swollen door with a shoulder",
            "ability": "strength",
            "dc": 14,
            "success": "The door gives way and the passage beyond stands open.",
        },
        {
            "action": "Turn the lock with a key that still fits it",
            "ability": "dexterity",
            "dc": 8,
            "success": "The lock turns without a sound and the door swings open.",
            "bypassed_by": ["rusty-key"],
        },
    ],
}

CAMPAIGN: dict = {
    "id": CAMPAIGN_ID,
    "title": "Hollow Reach",
    "summary": (
        "A flooded valley, a mill that stopped turning, and a warden who will not say why."
    ),
    "adventures": ["the-sunken-mill"],
    "seed_character": SEED_CHARACTER,
    "object_templates": [CREATURE_TEMPLATE, ITEM_TEMPLATE, FIXTURE_TEMPLATE],
}

SCENE_APPROACH: dict = {
    "id": "mill-approach",
    "title": "The Mill Approach",
    "truth": [
        "The mill leans into the flooded race; its wheel is jammed with black debris.",
        "The door is barred from the inside.",
    ],
    "consequences": ["Breaking the bar is loud, and anything inside the mill hears it."],
    "hidden": [
        {
            "fact": "Fresh bootprints lead into the mill and none lead out.",
            "ability": "wisdom",
            "skill": "Perception",
            "dc": 12,
            "discovered_by": "a Wisdom (Perception) check on the mud, or searching the bank",
        }
    ],
    "placements": [{"template": "rusty-key", "count": 1}],
    "exits": [
        {
            "id": "into-the-mill",
            "to": "mill-floor",
            "description": "The mill door, barred from within.",
            "condition": "the bar has been broken, forced, or lifted from outside",
        }
    ],
}

SCENE_FLOOR: dict = {
    "id": "mill-floor",
    "title": "The Milling Floor",
    "truth": [
        "Knee-deep water covers the floor; the grain chute above is dry.",
        "Two bog lurkers have made the flooded floor their nest.",
    ],
    "npc_intent": "The lurkers want to drag anything warm under the water and wait.",
    "consequences": ["Climbing to the dry grain chute puts the player out of the lurkers' reach."],
    "placements": [
        {
            "template": "bog-lurker",
            "count": 2,
            "carries": [{"template": "rusty-key", "count": 1}],
        },
        {"template": "sunken-door", "count": 1},
    ],
    "pressure": (
        "The water is still rising; the chute will be the only dry footing within the hour."
    ),
    "exits": [
        {
            "id": "out-of-the-mill",
            "kind": "adventure_end",
            "description": "The grain chute gives way onto the bank, and open air.",
        }
    ],
}

ADVENTURE: dict = {
    "id": "the-sunken-mill",
    "title": "The Sunken Mill",
    "intro": (
        "The rain stopped three days ago and the water has not gone down. "
        "The mill at the bend has not turned since, and nobody who went to "
        "look has come back to say why."
    ),
    "entry_scene": "mill-approach",
    "scenes": [SCENE_APPROACH, SCENE_FLOOR],
}


def campaign(**overrides) -> dict:
    data = copy.deepcopy(CAMPAIGN)
    data.update(overrides)
    return data


def adventure(**overrides) -> dict:
    data = copy.deepcopy(ADVENTURE)
    data.update(overrides)
    return data


def scene_approach(**overrides) -> dict:
    data = copy.deepcopy(SCENE_APPROACH)
    data.update(overrides)
    return data


def scene_floor(**overrides) -> dict:
    data = copy.deepcopy(SCENE_FLOOR)
    data.update(overrides)
    return data


def creature_template(**overrides) -> dict:
    data = copy.deepcopy(CREATURE_TEMPLATE)
    data.update(overrides)
    return data


def item_template(**overrides) -> dict:
    data = copy.deepcopy(ITEM_TEMPLATE)
    data.update(overrides)
    return data


def fixture_template(**overrides) -> dict:
    data = copy.deepcopy(FIXTURE_TEMPLATE)
    data.update(overrides)
    return data


def seed_character(**overrides) -> dict:
    data = copy.deepcopy(SEED_CHARACTER)
    data.update(overrides)
    return data


def abilities(**overrides) -> dict:
    data = copy.deepcopy(ABILITIES)
    data.update(overrides)
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def build_version_dir(
    root: Path,
    campaign_id: str = CAMPAIGN_ID,
    version: str = VERSION,
    *,
    campaign: dict | None = CAMPAIGN,  # noqa: F811 -- shadowing the factory is intentional here
    adventures: dict[str, dict] | None = None,
    scenes: dict[str, dict] | None = None,
    object_templates: list[dict] | None = None,
) -> Path:
    """Writes the fixture campaign (or the given overrides) under
    `root/campaigns/<campaign_id>/<version>/` and returns that directory.

    **step-1.4.md §4: two kinds of file.** There is no `definitions/`
    directory: `object_templates` overrides `campaign["object_templates"]`
    directly (default: the three templates above), and there is no separate
    per-template file to write.

    `scenes` is sugar over the single default adventure: pass a
    `dict[scene_id, scene_payload]` to override the *default* adventure's
    inline `scenes` list (order follows dict insertion order), or pass
    `adventures` directly when a test needs more than one adventure or a
    scene list that is not a simple override. `adventures` takes precedence
    over `scenes` when both are given.

    Pass `campaign=None` to write no `campaign.json` at all (R1); pass
    `object_templates=[]` to write a campaign with no templates (schema
    invalid by itself, per criterion 11 -- useful for a test that wants
    exactly that); pass `adventures={}` to write none.
    """
    if adventures is None:
        scene_list = list(scenes.values()) if scenes is not None else [SCENE_APPROACH, SCENE_FLOOR]
        adventures = {"the-sunken-mill": adventure(scenes=scene_list)}

    if campaign is not None and object_templates is not None:
        campaign = {**campaign, "object_templates": object_templates}

    version_dir = root / "campaigns" / campaign_id / version
    version_dir.mkdir(parents=True, exist_ok=True)
    if campaign is not None:
        write_json(version_dir / "campaign.json", campaign)
    for adventure_id, data in adventures.items():
        write_json(version_dir / "adventures" / f"{adventure_id}.json", data)
    return version_dir


@pytest.fixture
def content_root(tmp_path, monkeypatch):
    """Repoints `service.CONTENT_ROOT` at an empty `tmp_path`, through the
    module reference (D10) so `monkeypatch.setattr` actually takes effect."""
    monkeypatch.setattr(service, "CONTENT_ROOT", tmp_path)
    return tmp_path
