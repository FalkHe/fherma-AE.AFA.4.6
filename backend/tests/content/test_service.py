"""Tests for `app.modules.content.service` -- step-1.4.md §6 (the service
surface delta) and §7 (rules R12-R18).

Criterion numbers refer to `step-1.4.md` §10 ("The rules" 13-22, "The
service" 23-25). R1-R11 are unchanged in substance from the pre-rework suite
(they policed `campaign.json`/adventure-file mechanics untouched by this
step) and are covered here only by a couple of smoke tests to prove the
rework did not regress them -- the exhaustive per-rule coverage for R1-R11
already existed and this suite does not re-author it.
"""

import re

import pytest

from app.modules.content import errors, schemas, service
from tests.content.conftest import (
    CAMPAIGN_ID,
    VERSION,
    build_version_dir,
    campaign,
    creature_template,
    fixture_template,
    item_template,
    scene_approach,
    scene_floor,
    seed_character,
)

ENTRY_PATTERN = re.compile(r"^([^:]+): \[([A-Z0-9]+)\] (.+)$")


def _entries(exc_info):
    return [ENTRY_PATTERN.match(e) for e in exc_info.value.errors]


def _tags(exc_info):
    return [m.group(2) for m in _entries(exc_info)]


def _paths(exc_info):
    return [m.group(1) for m in _entries(exc_info)]


def _path_tag_pairs(exc_info):
    return {(m.group(1), m.group(2)) for m in _entries(exc_info)}


# --- Smoke: R1-R11 survive the rework -----------------------------------------


def test_valid_tree_loads_with_no_errors_smoke(content_root):
    build_version_dir(content_root)
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)
    assert set(loaded.object_templates.keys()) == {"bog-lurker", "rusty-key", "sunken-door"}


def test_r2_campaign_id_mismatch_still_fires_smoke(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))
    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)
    assert any(e.startswith("campaign.json: [R2]") for e in exc_info.value.errors)


# --- 13: a placement naming an undeclared template -> [R12] only -------------


def test_placement_unknown_template_yields_r12_only_c13(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(placements=[]),
            "mill-floor": scene_floor(placements=[{"template": "no-such-thing", "count": 1}]),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    pairs = [(m.group(1), m.group(2), m.group(3)) for m in _entries(exc_info)]
    r12 = [p for p in pairs if p[1] == "R12"]
    assert len(r12) == 1
    assert r12[0][0] == "adventures/the-sunken-mill.json"
    assert "mill-floor" in r12[0][2]
    assert "R17" not in _tags(exc_info)


# --- 14, 14a: carries[] / bypassed_by[] undeclared references ----------------


def test_carries_unknown_template_yields_one_r12_on_adventure_file_c14(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(placements=[]),
            "mill-floor": scene_floor(
                placements=[
                    {
                        "template": "bog-lurker",
                        "count": 1,
                        "carries": [{"template": "no-such-item", "count": 1}],
                    }
                ]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r12 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R12"]
    assert any(path == "adventures/the-sunken-mill.json" for path, _ in r12)


def test_bypassed_by_entry_unknown_template_yields_one_r12_on_campaign_json_c14(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "unlock it",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "opens",
                        "bypassed_by": ["no-such-item"],
                    },
                ]
            ),
        ],
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r12 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R12"]
    assert any(path == "campaign.json" and "sunken-door" in detail for path, detail in r12)


def test_bypassed_by_two_undeclared_entries_yields_two_r12_c14a(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "unlock it",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "opens",
                        "bypassed_by": ["no-such-item", "also-no-such-item"],
                    },
                ]
            ),
        ],
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r12_on_campaign = [
        m for m in _entries(exc_info) if m.group(2) == "R12" and m.group(1) == "campaign.json"
    ]
    assert len(r12_on_campaign) == 2


def test_bypassed_by_one_valid_one_undeclared_yields_exactly_one_r12_c14a(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "unlock it",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "opens",
                        "bypassed_by": ["rusty-key", "no-such-item"],
                    },
                ]
            ),
        ],
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r12_on_campaign = [
        m for m in _entries(exc_info) if m.group(2) == "R12" and m.group(1) == "campaign.json"
    ]
    assert len(r12_on_campaign) == 1


def test_bypassed_by_empty_list_yields_no_r12_c14a(content_root):
    build_version_dir(content_root)  # default fixture's first check has bypassed_by == []
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert loaded.object_templates["sunken-door"].checks[0].bypassed_by == []


# --- 15: R13, template id uniqueness ------------------------------------------


def test_duplicate_template_id_yields_one_r13_and_first_kept_c15(content_root):
    duplicate_key = item_template(name="Duplicate Rusty Key")
    build_version_dir(
        content_root,
        object_templates=[creature_template(), item_template(), duplicate_key, fixture_template()],
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r13 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R13"]
    assert len(r13) == 1
    assert r13[0][0] == "campaign.json"
    assert "rusty-key" in r13[0][1]
    # the duplicate trips no R15 of its own
    assert "R15" not in _tags(exc_info)


# --- 16: R14, orphan templates -------------------------------------------------


def test_unreferenced_template_yields_one_r14_c16(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            item_template(id="unused-item", name="Unused Item"),
            fixture_template(),
        ],
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        m.group(1) == "campaign.json" and m.group(2) == "R14" and "unused-item" in m.group(3)
        for m in _entries(exc_info)
    )


def test_template_referenced_only_by_a_carry_is_not_orphaned_c16(content_root):
    build_version_dir(content_root)  # rusty-key is carried by bog-lurker in mill-floor
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert "rusty-key" in loaded.object_templates


def test_template_referenced_only_as_first_bypassed_by_entry_is_not_orphaned_c16(content_root):
    # a second item, referenced only as the *first* entry of a bypassed_by list
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            item_template(id="lockpick", name="Lockpick"),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "unlock it",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "opens",
                        "bypassed_by": ["lockpick", "rusty-key"],
                    },
                ]
            ),
        ],
    )
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert "lockpick" in loaded.object_templates


def test_template_referenced_only_as_later_bypassed_by_entry_is_not_orphaned_c16(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            item_template(id="lockpick", name="Lockpick"),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "unlock it",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "opens",
                        "bypassed_by": ["rusty-key", "lockpick"],
                    },
                ]
            ),
        ],
    )
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert "lockpick" in loaded.object_templates


# --- 17: R15, name uniqueness --------------------------------------------------


def test_name_collision_case_insensitive_across_kinds_names_later_sorted_id_c17(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            fixture_template(),
            item_template(id="zzz-key", name="RUSTY KEY"),  # collides with rusty-key, case-only
        ],
        scenes={
            "mill-approach": scene_approach(
                placements=[
                    {"template": "rusty-key", "count": 1},
                    {"template": "zzz-key", "count": 1},
                ]
            ),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r15 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R15"]
    assert len(r15) == 1
    assert r15[0][0] == "campaign.json"
    assert "zzz-key" in r15[0][1]  # later of the two, sorted by id


# --- 18: R16, at most once per placement/carries list --------------------------


def test_duplicate_template_in_scene_placements_yields_one_r16_c18(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(placements=[]),
            "mill-floor": scene_floor(
                placements=[
                    {"template": "bog-lurker", "count": 1},
                    {"template": "bog-lurker", "count": 1},
                ]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r16 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R16"]
    assert len(r16) == 1
    assert r16[0][0] == "adventures/the-sunken-mill.json"
    assert "mill-floor" in r16[0][1]
    assert "bog-lurker" in r16[0][1]


def test_duplicate_template_in_one_placements_carries_list_yields_one_r16_c18(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(placements=[]),
            "mill-floor": scene_floor(
                placements=[
                    {
                        "template": "bog-lurker",
                        "count": 1,
                        "carries": [
                            {"template": "rusty-key", "count": 1},
                            {"template": "rusty-key", "count": 1},
                        ],
                    }
                ]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r16 = [m for m in _entries(exc_info) if m.group(2) == "R16"]
    assert len(r16) == 1


def test_same_template_once_in_placements_and_once_in_a_carry_is_not_flagged_c18(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(placements=[{"template": "rusty-key", "count": 1}]),
            "mill-floor": scene_floor(
                placements=[
                    {
                        "template": "bog-lurker",
                        "count": 1,
                        "carries": [{"template": "rusty-key", "count": 1}],
                    },
                    # keeps sunken-door referenced (R14) even though this
                    # override replaces the default mill-floor placements list
                    {"template": "sunken-door", "count": 1},
                ]
            ),
        },
    )
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert "rusty-key" in loaded.object_templates


# --- 19, 19a: R17, item-kind check on carries/bypassed_by ----------------------


def test_carries_non_item_template_yields_one_r17_on_adventure_file_c19(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(placements=[]),
            "mill-floor": scene_floor(
                placements=[
                    {
                        "template": "sunken-door",
                        "count": 1,
                        "carries": [{"template": "bog-lurker", "count": 1}],
                    }
                ]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r17 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R17"]
    assert len(r17) == 1
    assert r17[0][0] == "adventures/the-sunken-mill.json"


def test_bypassed_by_entry_non_item_yields_one_r17_on_campaign_json_c19(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "scare it off",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "it flees",
                        "bypassed_by": ["bog-lurker"],
                    },
                ]
            ),
        ],
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r17 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R17"]
    assert len(r17) == 1
    assert r17[0][0] == "campaign.json"
    assert "sunken-door" in r17[0][1]


def test_bypassed_by_one_item_one_creature_yields_exactly_one_r17_c19a(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            item_template(),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "get past it",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "past it",
                        "bypassed_by": ["rusty-key", "bog-lurker"],
                    },
                ]
            ),
        ],
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r17 = [m for m in _entries(exc_info) if m.group(2) == "R17"]
    assert len(r17) == 1
    # the item entry ("rusty-key") produces no finding of any kind
    assert not any("rusty-key" in m.group(3) and m.group(2) != "R14" for m in _entries(exc_info))


def test_bypassed_by_two_non_item_entries_yields_two_r17_c19a(content_root):
    build_version_dir(
        content_root,
        object_templates=[
            creature_template(),
            creature_template(id="second-lurker", name="Second Lurker"),
            item_template(),
            fixture_template(
                checks=[
                    fixture_template()["checks"][0],
                    {
                        "action": "get past it",
                        "ability": "dexterity",
                        "dc": 8,
                        "success": "past it",
                        "bypassed_by": ["bog-lurker", "second-lurker"],
                    },
                ]
            ),
        ],
        scenes={
            "mill-approach": scene_approach(placements=[]),
            "mill-floor": scene_floor(
                placements=[
                    {"template": "bog-lurker", "count": 1},
                    {"template": "second-lurker", "count": 1},
                    {"template": "sunken-door", "count": 1},
                ]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r17_on_campaign = [
        m for m in _entries(exc_info) if m.group(2) == "R17" and m.group(1) == "campaign.json"
    ]
    assert len(r17_on_campaign) == 2


# --- 20: R18, an item placement cannot carry ------------------------------------


def test_item_placement_with_carries_yields_one_r18_c20(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(
                placements=[
                    {
                        "template": "rusty-key",
                        "count": 1,
                        "carries": [{"template": "rusty-key", "count": 1}],
                    }
                ]
            ),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r18 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R18"]
    assert len(r18) == 1
    assert r18[0][0] == "adventures/the-sunken-mill.json"
    assert "rusty-key" in r18[0][1]


def test_creature_and_fixture_placements_with_carries_produce_no_r18_c20(content_root):
    build_version_dir(content_root)  # bog-lurker (creature) carries rusty-key
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert loaded.scenes["mill-floor"].placements[0].carries


# --- 21: the grammar of errors[] -------------------------------------------------


def test_every_error_entry_matches_the_pinned_grammar_c21(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    grammar = re.compile(r"^[^:]+(/[^:]+)*: \[(READ|SCHEMA|R([2-9]|1[0-9]|20))\] .+$")
    for entry in exc_info.value.errors:
        assert grammar.match(entry), entry
        assert "[R1]" not in entry
        assert "[R3]" not in entry


# --- 22: the worked example loads with an empty problem set --------------------


def test_default_fixture_tree_loads_with_no_rule_firing_c22(content_root):
    build_version_dir(content_root)
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert loaded.object_templates["sunken-door"].kind == "fixture"


# --- 23, 24, 25: the service surface ---------------------------------------------


def test_load_object_template_returns_fixture_template_c23(content_root):
    build_version_dir(content_root)
    template = service.load_object_template(CAMPAIGN_ID, VERSION, "sunken-door")
    assert isinstance(template, schemas.FixtureTemplate)


def test_load_definition_no_longer_exists_c23():
    assert not hasattr(service, "load_definition")


def test_load_object_template_unknown_id_raises_with_pinned_relative_path_c24(content_root):
    build_version_dir(content_root)

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_object_template(CAMPAIGN_ID, VERSION, "no-such-thing")

    assert (
        exc_info.value.relative_path
        == f"campaigns/{CAMPAIGN_ID}/{VERSION}/object-template/no-such-thing"
    )


def test_load_object_template_traversal_ids_never_reach_the_filesystem_c25(content_root):
    build_version_dir(content_root)

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_object_template(CAMPAIGN_ID, VERSION, "../campaign")
    assert (
        exc_info.value.relative_path
        == f"campaigns/{CAMPAIGN_ID}/{VERSION}/object-template/../campaign"
    )

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_object_template("../../app", VERSION, "bog-lurker")
    assert exc_info.value.relative_path == f"campaigns/../../app/{VERSION}"


# --- AC2: terminal-scene means "reachable and ends in an adventure_end exit" ---


def test_reachable_scene_with_adventure_end_exit_satisfies_terminal_rule_ac2(content_root):
    build_version_dir(content_root)
    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise
    assert loaded.scenes["mill-floor"].exits[0].kind == "adventure_end"


def test_scene_with_no_exits_at_all_is_refused_ac2(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(exits=[]),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert (
        "adventures/the-sunken-mill.json: [R10] no scene reachable from entry_scene "
        "carries an adventure_end exit"
    ) in exc_info.value.errors


def test_r9_ignores_adventure_end_exits_but_still_fires_for_scene_exits_ac2(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(
                exits=[
                    {
                        "id": "into-the-mill",
                        "to": "no-such-scene",
                        "description": "The mill door, barred from within.",
                    }
                ]
            ),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r9 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R9"]
    assert len(r9) == 1
    assert r9[0][0] == "adventures/the-sunken-mill.json"
    assert "no-such-scene" in r9[0][1]


# --- AC3: R19, duplicate exit id within one scene -------------------------------


def test_duplicate_exit_id_in_one_scene_yields_one_r19_ac3(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(
                exits=[
                    {
                        "id": "into-the-mill",
                        "to": "mill-floor",
                        "description": "The mill door, barred from within.",
                    },
                    {
                        "id": "into-the-mill",
                        "to": "mill-floor",
                        "description": "A second, unbarred door.",
                    },
                ]
            ),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r19 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R19"]
    assert len(r19) == 1
    assert r19[0][0] == "adventures/the-sunken-mill.json"
    assert "mill-approach" in r19[0][1]
    assert "into-the-mill" in r19[0][1]


# --- AC3: R20, seed character inventory names an item template -----------------


def test_seed_inventory_unknown_template_yields_one_r20_ac3(content_root):
    build_version_dir(
        content_root,
        campaign=campaign(seed_character=seed_character(inventory=["no-such-item"])),
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r20 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R20"]
    assert len(r20) == 1
    assert r20[0][0] == "campaign.json"
    assert "no-such-item" in r20[0][1]
    assert "unknown object template" in r20[0][1]


def test_seed_inventory_non_item_template_yields_one_r20_ac3(content_root):
    build_version_dir(
        content_root,
        campaign=campaign(seed_character=seed_character(inventory=["bog-lurker"])),
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r20 = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R20"]
    assert len(r20) == 1
    assert r20[0][0] == "campaign.json"
    assert "bog-lurker" in r20[0][1]
    assert "is not an item" in r20[0][1]


def test_seed_inventory_entry_counts_as_r14_reference_ac3(content_root):
    extra_item = item_template(id="spare-key", name="Spare Key")
    build_version_dir(
        content_root,
        object_templates=[creature_template(), item_template(), extra_item, fixture_template()],
        campaign=campaign(seed_character=seed_character(inventory=["rusty-key", "spare-key"])),
    )

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise: spare-key is referenced
    assert "spare-key" in loaded.object_templates
