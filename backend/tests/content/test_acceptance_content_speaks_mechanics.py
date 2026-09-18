"""qa acceptance tests -- sprint 005/01 "the content speaks the mechanics'
language"
(docs/intents/005-game-state-services/sprints/01-content-speaks-mechanics/brief.md).

Black-box over `app.modules.content.service.load_campaign` and the
`app content validate` CLI only -- this file never imports
`app.modules.content.schemas` or reads `schemas.py` / `service.py`, and it
owns no fixtures beyond the two-scene layout below (built from the shared
`tests/content/conftest.py` factories, which is the harness every suite in
this package already uses).

Written against the sprint brief and interface contracts, not against the
implementation landing in parallel -- every test here is expected to fail
now (a missing `Exit.id`/`Exit.kind`, the old `exits == []` terminal rule,
or the still-prose `SeedCharacter.inventory`), and to pass once that work
lands.
"""

import re

import pytest
from typer.testing import CliRunner

from app.modules.content import errors, service
from app.modules.content.commands import content_app
from tests.content.conftest import (
    CAMPAIGN_ID,
    VERSION,
    build_version_dir,
    campaign,
    scene_approach,
    scene_floor,
    seed_character,
)

runner = CliRunner()

ENTRY_PATTERN = re.compile(r"^([^:]+): \[([A-Za-z0-9]+)\] (.+)$")


def _entries(exc_info):
    return [ENTRY_PATTERN.match(e) for e in exc_info.value.errors]


def _tags(exc_info):
    return [m.group(2) for m in _entries(exc_info) if m]


def _scenes_with_terminal_exit(**overrides):
    """The shared two-scene `hollow-reach` layout, wired so it satisfies the
    new `Exit` contract by default: `mill-approach` carries one `scene` exit
    (with `id` and `to`) into `mill-floor`, and `mill-floor` carries one
    `adventure_end` exit (with `id`, no `to`) that ends the adventure. Every
    other field (placements, truth, etc.) is untouched, so any override here
    isolates exactly the behaviour a test wants to exercise.
    """
    scenes = {
        "mill-approach": scene_approach(
            exits=[
                {
                    "id": "into-the-mill",
                    "kind": "scene",
                    "to": "mill-floor",
                    "description": "The mill door, barred from within.",
                }
            ]
        ),
        "mill-floor": scene_floor(
            exits=[
                {
                    "id": "leave-the-mill",
                    "kind": "adventure_end",
                    "description": "Climb out through the grain chute into daylight.",
                }
            ]
        ),
    }
    scenes.update(overrides)
    return scenes


# --- AC1 ----------------------------------------------------------------------


def test_ac1_adventure_end_exit_needs_no_to_but_a_scene_exit_does(content_root):
    """← AC1"""
    # an adventure whose ending exit carries no `to` loads
    build_version_dir(content_root, scenes=_scenes_with_terminal_exit())
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert loaded.scenes["mill-floor"].exits[0].kind == "adventure_end"

    # a `scene` exit without `to` is refused, via the loader's [SCHEMA] tag
    build_version_dir(
        content_root,
        scenes=_scenes_with_terminal_exit(
            **{
                "mill-approach": scene_approach(
                    exits=[
                        {
                            "id": "into-the-mill",
                            "kind": "scene",
                            "description": "The mill door, barred from within.",
                        }
                    ]
                )
            }
        ),
    )
    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    schema_entries = [m for m in _entries(exc_info) if m and m.group(2) == "SCHEMA"]
    assert schema_entries
    assert schema_entries[0].group(1) == "adventures/the-sunken-mill.json"


# --- AC2 ------------------------------------------------------------------------


def test_ac2_terminal_scene_must_be_reachable_and_carry_an_adventure_end_exit(content_root):
    """← AC2"""
    # the last scene carries an adventure_end exit: validates
    build_version_dir(content_root, scenes=_scenes_with_terminal_exit())
    service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise

    # the last scene has no exits at all: refused
    build_version_dir(
        content_root,
        scenes=_scenes_with_terminal_exit(**{"mill-floor": scene_floor(exits=[])}),
    )
    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r10 = [m for m in _entries(exc_info) if m and m.group(2) == "R10"]
    assert r10
    assert r10[0].group(1) == "adventures/the-sunken-mill.json"


# --- AC3 --------------------------------------------------------------------------


def test_ac3_duplicate_exit_id_and_bad_inventory_entries_are_refused(content_root):
    """← AC3"""
    # two exits sharing one id in a single scene: refused, naming the scene and the id
    build_version_dir(
        content_root,
        scenes=_scenes_with_terminal_exit(
            **{
                "mill-approach": scene_approach(
                    exits=[
                        {
                            "id": "leave",
                            "kind": "scene",
                            "to": "mill-floor",
                            "description": "The mill door, barred from within.",
                        },
                        {
                            "id": "leave",
                            "kind": "scene",
                            "to": "mill-floor",
                            "description": "A second way through the same door.",
                        },
                    ]
                )
            }
        ),
    )
    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r19 = [m for m in _entries(exc_info) if m and m.group(2) == "R19"]
    assert len(r19) == 1
    assert r19[0].group(1) == "adventures/the-sunken-mill.json"
    assert "mill-approach" in r19[0].group(3)
    assert "leave" in r19[0].group(3)

    # a seed-character inventory entry naming nothing known: refused
    build_version_dir(
        content_root,
        scenes=_scenes_with_terminal_exit(),
        campaign=campaign(seed_character=seed_character(inventory=["no-such-item"])),
    )
    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r20_unknown = [m for m in _entries(exc_info) if m and m.group(2) == "R20"]
    assert r20_unknown
    assert r20_unknown[0].group(1) == "campaign.json"
    assert "no-such-item" in r20_unknown[0].group(3)

    # a seed-character inventory entry naming a creature template, not an item: refused
    build_version_dir(
        content_root,
        scenes=_scenes_with_terminal_exit(),
        campaign=campaign(seed_character=seed_character(inventory=["bog-lurker"])),
    )
    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r20_not_item = [m for m in _entries(exc_info) if m and m.group(2) == "R20"]
    assert r20_not_item
    assert r20_not_item[0].group(1) == "campaign.json"
    assert "bog-lurker" in r20_not_item[0].group(3)


# --- AC4 ----------------------------------------------------------------------------


def test_ac4_shipped_tree_validates_and_lair_hollow_ends_the_adventure():
    """← AC4. Runs over the real, shipped `backend/content/` tree -- no
    `content_root` fixture, no monkeypatching, matching `test_shipped_tree.py`.
    """
    result = runner.invoke(content_app, [])

    assert result.exit_code == 0
    assert "greenhollow/v1: ok" in result.stdout

    loaded = service.load_campaign("greenhollow", "v1")
    lair_hollow = loaded.scenes["lair-hollow"]
    assert any(exit_.kind == "adventure_end" for exit_ in lair_hollow.exits)
