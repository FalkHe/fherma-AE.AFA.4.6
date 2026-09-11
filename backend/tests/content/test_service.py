"""Tests for `app.modules.content.service` -- the loader, the id/version
validation guard (phase contract §5.1) and the referential rule set (§11).

Criterion numbers refer to `step-1.1.md` §6 ("Loading" 9-17, "Error
reporting" 18-24, "The referential rules" 25-41).
"""

import re
import shutil

import pytest
from app.modules.content import errors, service

from tests.content.conftest import (
    CAMPAIGN_ID,
    VERSION,
    adventure,
    build_version_dir,
    campaign,
    definition,
    scene_approach,
    scene_floor,
    write_json,
)

ENTRY_PATTERN = re.compile(r"^([^:]+): \[([A-Z0-9]+)\] (.+)$")


def _entries(exc_info):
    return [ENTRY_PATTERN.match(e) for e in exc_info.value.errors]


def _tags(exc_info):
    return [m.group(2) for m in _entries(exc_info)]


def _paths(exc_info):
    return [m.group(1) for m in _entries(exc_info)]


# --- Loading (criteria 9-17) -------------------------------------------------


def test_load_campaign_returns_loaded_campaign_c9(content_root):
    build_version_dir(content_root)

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)

    assert loaded.version == VERSION
    assert list(loaded.adventures.keys()) == ["the-sunken-mill"]
    assert set(loaded.scenes.keys()) == {"mill-approach", "mill-floor"}
    assert set(loaded.definitions.keys()) == {"bog-lurker"}


def test_load_scene_and_load_definition_c10(content_root):
    build_version_dir(content_root)

    scene = service.load_scene(CAMPAIGN_ID, VERSION, "mill-floor")
    assert scene.id == "mill-floor"

    found_definition = service.load_definition(CAMPAIGN_ID, VERSION, "bog-lurker")
    assert found_definition.id == "bog-lurker"


def test_list_campaign_ids_sorted_and_empty_raises_nothing_c11(content_root):
    assert service.list_campaign_ids() == []

    build_version_dir(content_root, campaign_id="zeta-quest", campaign=campaign(id="zeta-quest"))
    build_version_dir(content_root, campaign_id="alpha-quest", campaign=campaign(id="alpha-quest"))

    assert service.list_campaign_ids() == ["alpha-quest", "zeta-quest"]


def test_list_versions_sorted_numerically_and_not_found_c12(content_root):
    build_version_dir(content_root, version="v2")
    build_version_dir(content_root, version="v10")

    assert service.list_versions(CAMPAIGN_ID) == ["v2", "v10"]

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.list_versions("no-such-campaign")
    assert exc_info.value.relative_path == "campaigns/no-such-campaign"


def test_load_campaign_missing_version_directory_c13(content_root):
    build_version_dir(content_root)

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, "v9")
    assert exc_info.value.relative_path == f"campaigns/{CAMPAIGN_ID}/v9"


def test_load_scene_and_definition_unknown_id_c14(content_root):
    build_version_dir(content_root)

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_scene(CAMPAIGN_ID, VERSION, "no-such-scene")
    assert (
        exc_info.value.relative_path
        == f"campaigns/{CAMPAIGN_ID}/{VERSION}/scenes/no-such-scene.json"
    )

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_definition(CAMPAIGN_ID, VERSION, "no-such-definition")
    assert (
        exc_info.value.relative_path
        == f"campaigns/{CAMPAIGN_ID}/{VERSION}/definitions/no-such-definition.json"
    )


def test_non_json_file_in_scenes_is_ignored_c15(content_root):
    version_dir = build_version_dir(content_root)
    (version_dir / "scenes" / "notes.md").write_text("not loaded, not reported")

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)

    assert set(loaded.scenes.keys()) == {"mill-approach", "mill-floor"}


def test_missing_definitions_directory_is_r14_not_oserror_c16(content_root):
    version_dir = build_version_dir(content_root)
    shutil.rmtree(version_dir / "definitions")

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert "R14" in _tags(exc_info)


@pytest.mark.parametrize(
    "call",
    [
        lambda: service.load_campaign("../x", "v1"),
        lambda: service.load_campaign(CAMPAIGN_ID, "../v1"),
        lambda: service.load_scene(CAMPAIGN_ID, VERSION, "../campaign"),
    ],
)
def test_id_arguments_never_reach_the_filesystem_c17(content_root, call):
    # A readable file sits just outside CONTENT_ROOT. If any of these calls
    # built a path before validating, it could read this file instead of
    # raising ContentNotFoundError.
    (content_root.parent / "secret.json").write_text('{"leak": true}')
    build_version_dir(content_root)

    with pytest.raises(errors.ContentNotFoundError):
        call()


# --- Error reporting (criteria 18-24) ---------------------------------------


def test_every_error_entry_matches_the_pinned_grammar_c18(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    grammar = re.compile(r"^[^:]+(/[^:]+)*: \[(READ|SCHEMA|R2|R([4-9]|1[0-8]))\] .+$")
    for entry in exc_info.value.errors:
        assert grammar.match(entry), entry


def test_errors_sorted_and_deterministic_between_calls_c19(content_root):
    build_version_dir(
        content_root,
        adventures={
            "the-sunken-mill": adventure(scenes=["mill-approach", "mill-floor", "ghost-scene"])
        },
    )

    with pytest.raises(errors.ContentInvalidError) as first:
        service.load_campaign(CAMPAIGN_ID, VERSION)
    with pytest.raises(errors.ContentInvalidError) as second:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert first.value.errors == sorted(first.value.errors)
    assert first.value.errors == second.value.errors


def test_broken_scene_and_broken_definition_both_reported_c20(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(creatures=[{"definition": "no-such-thing", "count": 1}]),
        },
        definitions={"bog-lurker": definition(id="other")},
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    tags = _tags(exc_info)
    assert "R14" in tags
    assert "R15" in tags


def test_malformed_campaign_json_is_exactly_one_read_entry_c21(content_root):
    version_dir = build_version_dir(content_root)
    (version_dir / "campaign.json").write_text("{not valid json")

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].startswith("campaign.json: [READ]")


def test_schema_invalid_campaign_json_is_exactly_one_schema_entry_c22(content_root):
    version_dir = build_version_dir(content_root)
    write_json(version_dir / "campaign.json", {"id": "hollow-reach"})

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].startswith("campaign.json: [SCHEMA]")


def test_model_level_schema_failure_has_no_empty_location_segment_c23(content_root):
    version_dir = build_version_dir(content_root)
    (version_dir / "scenes" / "mill-floor.json").write_text("[]")

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    schema_entries = [e for e in exc_info.value.errors if "[SCHEMA]" in e]
    assert schema_entries
    for entry in schema_entries:
        assert ": : " not in entry


def test_content_invalid_error_str_and_empty_errors_guard_c24():
    exc = errors.ContentInvalidError("hollow-reach", "v1", ["a: [READ] boom"])
    text = str(exc)
    assert "hollow-reach" in text
    assert "v1" in text
    assert "1" in text

    errors.ContentInvalidError("hollow-reach", "v1", [])  # must not raise


# --- The referential rules (criteria 25-41) ---------------------------------


def test_r1_missing_campaign_json_c25(content_root):
    version_dir = build_version_dir(content_root)
    (version_dir / "campaign.json").unlink()

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].startswith("campaign.json: [READ]")


def test_r2_campaign_id_does_not_match_directory_name_c26(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("campaign.json: [R2]") for e in exc_info.value.errors)


def test_r4_unknown_adventure_id_c27(content_root):
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "no-such-adventure"]),
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("campaign.json: [R4]") for e in exc_info.value.errors)


def test_r4_duplicate_adventure_deduplicated_before_r8_c27(content_root):
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "the-sunken-mill"]),
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    tags = _tags(exc_info)
    assert "R4" in tags
    assert "R8" not in tags


def test_r5_orphan_adventure_file_c28(content_root):
    build_version_dir(
        content_root,
        adventures={
            "the-sunken-mill": adventure(),
            "orphan": adventure(id="orphan", entry_scene="mill-approach"),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("adventures/orphan.json: [R5]") for e in exc_info.value.errors)


def test_r6_adventure_id_does_not_match_filename_stem_c29(content_root):
    build_version_dir(content_root, adventures={"the-sunken-mill": adventure(id="other")})

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("adventures/the-sunken-mill.json: [R6]") for e in exc_info.value.errors)


def test_r7_unknown_scene_id_in_adventure_c30(content_root):
    build_version_dir(
        content_root,
        adventures={
            "the-sunken-mill": adventure(scenes=["mill-approach", "mill-floor", "no-such-scene"])
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("adventures/the-sunken-mill.json: [R7]") for e in exc_info.value.errors)


def test_r7_duplicate_scene_id_in_adventure_c30(content_root):
    build_version_dir(
        content_root,
        adventures={
            "the-sunken-mill": adventure(scenes=["mill-approach", "mill-floor", "mill-floor"])
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("adventures/the-sunken-mill.json: [R7]") for e in exc_info.value.errors)


def test_r8_orphan_scene_file_c31(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(),
            "orphan": scene_floor(id="orphan", creatures=[]),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("scenes/orphan.json: [R8]") for e in exc_info.value.errors)


def test_r8_scene_claimed_by_two_adventures_names_the_second_c31(content_root):
    second_adventure = adventure(
        id="second-adventure", entry_scene="mill-floor", scenes=["mill-floor"]
    )
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "second-adventure"]),
        adventures={"the-sunken-mill": adventure(), "second-adventure": second_adventure},
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        e.startswith("adventures/second-adventure.json: [R8]") for e in exc_info.value.errors
    )


def test_r9_scene_id_does_not_match_filename_stem_c32(content_root):
    build_version_dir(
        content_root,
        scenes={"mill-approach": scene_approach(), "mill-floor": scene_floor(id="other")},
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("scenes/mill-floor.json: [R9]") for e in exc_info.value.errors)


def test_r10_entry_scene_not_in_adventure_scenes_c33(content_root):
    build_version_dir(
        content_root, adventures={"the-sunken-mill": adventure(entry_scene="no-such-scene")}
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        e.startswith("adventures/the-sunken-mill.json: [R10]") for e in exc_info.value.errors
    )


def test_r11_exit_targets_unknown_scene_c34(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(
                exits=[{"to": "under-whee", "description": "d", "condition": None}]
            ),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("scenes/mill-approach.json: [R11]") for e in exc_info.value.errors)


def test_r11_exit_targets_own_scene_c34(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(
                exits=[{"to": "mill-approach", "description": "d", "condition": None}]
            ),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("scenes/mill-approach.json: [R11]") for e in exc_info.value.errors)


def test_r11_exit_targets_scene_in_a_different_adventure_c34(content_root):
    other_scene = scene_floor(id="other-scene", creatures=[])
    other_adventure = adventure(
        id="other-adventure", entry_scene="other-scene", scenes=["other-scene"]
    )
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "other-adventure"]),
        adventures={"the-sunken-mill": adventure(), "other-adventure": other_adventure},
        scenes={
            "mill-approach": scene_approach(
                exits=[{"to": "other-scene", "description": "d", "condition": None}]
            ),
            "mill-floor": scene_floor(),
            "other-scene": other_scene,
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("scenes/mill-approach.json: [R11]") for e in exc_info.value.errors)


def test_r12_no_terminal_scene_c35(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(
                exits=[{"to": "mill-approach", "description": "back", "condition": None}]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        e.startswith("adventures/the-sunken-mill.json: [R12]") for e in exc_info.value.errors
    )


def test_r13_scene_unreachable_from_entry_scene_c36(content_root):
    build_version_dir(
        content_root,
        adventures={
            "the-sunken-mill": adventure(scenes=["mill-approach", "mill-floor", "isolated"])
        },
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(),
            "isolated": scene_floor(id="isolated", creatures=[]),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        e.startswith("adventures/the-sunken-mill.json: [R13]") for e in exc_info.value.errors
    )


def test_r13_scene_reachable_only_through_a_conditioned_exit_is_not_flagged_c36(content_root):
    build_version_dir(content_root)  # mill-floor is reached only via a conditioned exit

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise

    assert set(loaded.scenes.keys()) == {"mill-approach", "mill-floor"}


def test_r13_single_scene_adventure_is_not_flagged_unreachable_c36(content_root):
    single_scene_adventure = adventure(scenes=["mill-approach"], entry_scene="mill-approach")
    build_version_dir(
        content_root,
        adventures={"the-sunken-mill": single_scene_adventure},
        scenes={"mill-approach": scene_approach(exits=[])},
        definitions={},
    )

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise

    assert list(loaded.adventures.keys()) == ["the-sunken-mill"]


def test_r14_creature_placement_targets_unknown_definition_c37(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(creatures=[{"definition": "no-such-thing", "count": 1}]),
        },
        definitions={},
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("scenes/mill-floor.json: [R14]") for e in exc_info.value.errors)


def test_r15_definition_id_does_not_match_filename_stem_c38(content_root):
    build_version_dir(content_root, definitions={"bog-lurker": definition(id="other")})

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("definitions/bog-lurker.json: [R15]") for e in exc_info.value.errors)


def test_r16_unreferenced_definition_c39(content_root):
    build_version_dir(
        content_root,
        definitions={
            "bog-lurker": definition(),
            "unused": definition(id="unused", name="Unused Thing"),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("definitions/unused.json: [R16]") for e in exc_info.value.errors)


def test_r17_three_way_name_collision_case_insensitive_c40(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(
                creatures=[
                    {"definition": "bog-lurker", "count": 1},
                    {"definition": "bog-lurker-2", "count": 1},
                    {"definition": "bog-lurker-3", "count": 1},
                ]
            ),
        },
        definitions={
            "bog-lurker": definition(),
            "bog-lurker-2": definition(id="bog-lurker-2", name="bog lurker"),
            "bog-lurker-3": definition(id="bog-lurker-3", name="Bog Lurker"),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    path_tag_pairs = set(zip(_paths(exc_info), _tags(exc_info), strict=True))
    assert ("definitions/bog-lurker-2.json", "R17") in path_tag_pairs
    assert ("definitions/bog-lurker-3.json", "R17") in path_tag_pairs
    assert ("definitions/bog-lurker.json", "R17") not in path_tag_pairs


def test_r18_definition_placed_twice_in_one_scene_c41(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(
                creatures=[
                    {"definition": "bog-lurker", "count": 1},
                    {"definition": "bog-lurker", "count": 1},
                ]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("scenes/mill-floor.json: [R18]") for e in exc_info.value.errors)
