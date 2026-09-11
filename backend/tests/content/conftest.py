"""Fixtures and content-tree builders shared by `tests/content/`.

Mode-A note (phase-1 shared-knowledge.md §8, P1-D13): `app.modules.content`
does not exist yet, so every test in this package fails to collect until
step 1.1 lands `backend/app/modules/content/`. That is expected.

**P1-D20 rework.** An adventure is one file, its scenes inline
(`Adventure.scenes: list[Scene]`). There is no `scenes/` directory and no
per-scene file: `build_version_dir` writes only `campaign.json`,
`adventures/<id>.json` and `definitions/<id>.json`.

Nothing here is committed as a fixture corpus (§8): `build_version_dir`
writes the §4.1 worked example (or a deliberately broken variant of it) into
`tmp_path` for the duration of one test, and `content_root` repoints
`service.CONTENT_ROOT` there via `monkeypatch.setattr` -- never
`from app.modules.content.service import CONTENT_ROOT`, which would rebind
the value and make the monkeypatch silently miss (D10 / phase-1 §5.1).
"""

import copy
import json
from pathlib import Path

import pytest

from app.modules.content import service

CAMPAIGN_ID = "hollow-reach"
VERSION = "v1"

CAMPAIGN: dict = {
    "id": CAMPAIGN_ID,
    "title": "Hollow Reach",
    "summary": (
        "A flooded valley, a mill that stopped turning, and a warden who will not say why."
    ),
    "adventures": ["the-sunken-mill"],
    "seed_character": {
        "name": "Perrin Ashdown",
        "race": "Halfling",
        "character_class": "Rogue",
        "background": ("A river-barge thief who owes the warden a favour and would rather not."),
        "appearance": (
            "Small, weather-browned, with a river-knotted braid and a coat two sizes too large."
        ),
        "abilities": {
            "strength": 9,
            "dexterity": 16,
            "constitution": 12,
            "intelligence": 11,
            "wisdom": 13,
            "charisma": 14,
        },
        "max_hp": 9,
        "armour_class": 14,
        "inventory": ["a shortsword", "a coil of rope", "a tin lantern"],
    },
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
            "dc": 12,
            "discovered_by": "a Wisdom (Perception) check on the mud, or searching the bank",
        }
    ],
    "exits": [
        {
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
    "creatures": [{"definition": "bog-lurker", "count": 2}],
    "pressure": (
        "The water is still rising; the chute will be the only dry footing within the hour."
    ),
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

DEFINITION: dict = {
    "id": "bog-lurker",
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
        "abilities": {
            "strength": 14,
            "dexterity": 13,
            "constitution": 12,
            "intelligence": 2,
            "wisdom": 11,
            "charisma": 4,
        },
        "attacks": [{"name": "Bite", "to_hit": 4, "damage": "1d6+2"}],
        "traits": ["Cannot be seen under still water without a deliberate search."],
    },
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


def definition(**overrides) -> dict:
    data = copy.deepcopy(DEFINITION)
    data.update(overrides)
    return data


def seed_character(**overrides) -> dict:
    data = copy.deepcopy(CAMPAIGN["seed_character"])
    data.update(overrides)
    return data


def abilities(**overrides) -> dict:
    data = {
        "strength": 9,
        "dexterity": 16,
        "constitution": 12,
        "intelligence": 11,
        "wisdom": 13,
        "charisma": 14,
    }
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
    definitions: dict[str, dict] | None = None,
) -> Path:
    """Writes the phase contract §4.1 worked example (or the given overrides)
    under `root/campaigns/<campaign_id>/<version>/` and returns that
    directory.

    P1-D20: there is no `scenes/` directory any more -- a scene is an element
    of its adventure's `scenes` list. `scenes` here is therefore sugar over
    the single default adventure: pass a `dict[scene_id, scene_payload]` to
    override the *default* adventure's inline `scenes` list (order follows
    dict insertion order), or pass `adventures` directly when a test needs
    more than one adventure or a scene list that is not a simple override.
    `adventures` takes precedence over `scenes` when both are given.

    Pass `campaign=None` to write no `campaign.json` at all (R1); pass
    `definitions={}` / `adventures={}` to write none of that kind.
    `scenes={}` yields an adventure with an empty `scenes` list -- schema
    invalid by itself (`Adventure.scenes` has `min_length=1`), useful for a
    test that wants exactly that.
    """
    if adventures is None:
        scene_list = list(scenes.values()) if scenes is not None else [SCENE_APPROACH, SCENE_FLOOR]
        adventures = {"the-sunken-mill": adventure(scenes=scene_list)}
    if definitions is None:
        definitions = {"bog-lurker": DEFINITION}

    version_dir = root / "campaigns" / campaign_id / version
    version_dir.mkdir(parents=True, exist_ok=True)
    if campaign is not None:
        write_json(version_dir / "campaign.json", campaign)
    for adventure_id, data in adventures.items():
        write_json(version_dir / "adventures" / f"{adventure_id}.json", data)
    for definition_id, data in definitions.items():
        write_json(version_dir / "definitions" / f"{definition_id}.json", data)
    return version_dir


@pytest.fixture
def content_root(tmp_path, monkeypatch):
    """Repoints `service.CONTENT_ROOT` at an empty `tmp_path`, through the
    module reference (D10) so `monkeypatch.setattr` actually takes effect."""
    monkeypatch.setattr(service, "CONTENT_ROOT", tmp_path)
    return tmp_path
