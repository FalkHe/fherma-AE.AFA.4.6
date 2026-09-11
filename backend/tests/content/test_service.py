"""Tests for `app.modules.content.service` -- the loader, the id/version
validation guard (phase contract §5.1) and the referential rule set (§11).

Criterion numbers refer to `step-1.1.md` §6 ("Loading" 11-19, "Error
reporting" 20-27, "The referential rules" 28-42).

**P1-D20 rework.** An adventure is one file, its scenes inline. The old R7, R8
and R9 (which policed the multi-file scene layout) are gone, not renumbered --
a scene cannot be orphaned or claimed by two adventures by construction, so
the six tests that proved those rules are deleted rather than carried
forward. A new R8 (scene id unique across the whole campaign) replaces them.
The rest of the rule list shifts down: old R10..R18 become new R7..R16 (see
`shared-knowledge.md` §11's old->new map). Every rule that used to be
reported on a scene's own file (`scenes/<id>.json`) is now reported on its
*adventure* file, with the scene id folded into the detail.
"""

import re
import shutil
import unittest.mock
from pathlib import Path

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


# --- Loading (criteria 11-19) ------------------------------------------------


def test_load_campaign_returns_loaded_campaign_c11(content_root):
    build_version_dir(content_root)

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)

    assert loaded.version == VERSION
    assert list(loaded.adventures.keys()) == ["the-sunken-mill"]
    assert set(loaded.scenes.keys()) == {"mill-approach", "mill-floor"}
    assert set(loaded.definitions.keys()) == {"bog-lurker"}


def test_load_scene_and_load_definition_c12(content_root):
    build_version_dir(content_root)

    scene = service.load_scene(CAMPAIGN_ID, VERSION, "mill-floor")
    assert scene.id == "mill-floor"

    found_definition = service.load_definition(CAMPAIGN_ID, VERSION, "bog-lurker")
    assert found_definition.id == "bog-lurker"


def test_list_campaign_ids_sorted_and_empty_raises_nothing_c13(content_root):
    assert service.list_campaign_ids() == []

    build_version_dir(content_root, campaign_id="zeta-quest", campaign=campaign(id="zeta-quest"))
    build_version_dir(content_root, campaign_id="alpha-quest", campaign=campaign(id="alpha-quest"))

    assert service.list_campaign_ids() == ["alpha-quest", "zeta-quest"]


def test_list_versions_sorted_numerically_and_not_found_c14(content_root):
    build_version_dir(content_root, version="v2")
    build_version_dir(content_root, version="v10")

    assert service.list_versions(CAMPAIGN_ID) == ["v2", "v10"]

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.list_versions("no-such-campaign")
    assert exc_info.value.relative_path == "campaigns/no-such-campaign"


def test_load_campaign_missing_version_directory_c15(content_root):
    build_version_dir(content_root)

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, "v9")
    assert exc_info.value.relative_path == f"campaigns/{CAMPAIGN_ID}/v9"


def test_load_scene_and_definition_unknown_id_c16(content_root):
    build_version_dir(content_root)

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_scene(CAMPAIGN_ID, VERSION, "no-such-scene")
    # P1-D20 (§6.1): a scene is a logical address, singular "scene", no
    # ".json" -- there is no scene file to name.
    assert exc_info.value.relative_path == f"campaigns/{CAMPAIGN_ID}/{VERSION}/scene/no-such-scene"

    with pytest.raises(errors.ContentNotFoundError) as exc_info:
        service.load_definition(CAMPAIGN_ID, VERSION, "no-such-definition")
    assert (
        exc_info.value.relative_path
        == f"campaigns/{CAMPAIGN_ID}/{VERSION}/definitions/no-such-definition.json"
    )


def test_non_json_file_in_adventures_is_ignored_c17(content_root):
    version_dir = build_version_dir(content_root)
    (version_dir / "adventures" / "notes.md").write_text("not loaded, not reported")

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)

    assert set(loaded.scenes.keys()) == {"mill-approach", "mill-floor"}


def test_missing_definitions_directory_is_r12_not_oserror_c18(content_root):
    version_dir = build_version_dir(content_root)
    shutil.rmtree(version_dir / "definitions")

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    # No definitions directory at all: mill-floor's placement of bog-lurker
    # cannot resolve -> R12 (creatures[].definition resolves to a file), not
    # an OSError and not R14 (there is no orphan definition *file* to report).
    assert "R12" in _tags(exc_info)


@pytest.mark.parametrize(
    ("call", "expected_relative_path"),
    [
        (lambda: service.load_campaign("../x", "v1"), "campaigns/../x/v1"),
        (
            lambda: service.load_campaign(CAMPAIGN_ID, "../v1"),
            f"campaigns/{CAMPAIGN_ID}/../v1",
        ),
        (
            lambda: service.load_scene(CAMPAIGN_ID, VERSION, "../campaign"),
            f"campaigns/{CAMPAIGN_ID}/{VERSION}/scene/../campaign",
        ),
    ],
)
def test_id_arguments_never_reach_the_filesystem_c19(content_root, call, expected_relative_path):
    # A readable, parseable file sits just outside CONTENT_ROOT. If any of
    # these calls built a path before validating the id/version pattern, a
    # naive ".." join could resolve onto this file instead of raising
    # ContentNotFoundError -- so this is a stronger proof than "raises the
    # right exception type": the sentinel's presence and content are what
    # a leak would expose.
    sentinel = content_root.parent / "secret.json"
    sentinel.write_text('{"leak": true}')

    original_read_text = Path.read_text

    def guarded_read_text(self, *args, **kwargs):
        assert content_root in self.parents, (
            f"content module attempted to read {self} outside CONTENT_ROOT"
        )
        return original_read_text(self, *args, **kwargs)

    with unittest.mock.patch.object(Path, "read_text", guarded_read_text):
        build_version_dir(content_root)

        with pytest.raises(errors.ContentNotFoundError) as exc_info:
            call()

    assert exc_info.value.relative_path == expected_relative_path
    # The sentinel was never touched: content is still exactly what we wrote,
    # never re-serialised through a Pydantic model that would drop the key.
    assert sentinel.read_text() == '{"leak": true}'


# --- Error reporting (criteria 20-27) ----------------------------------------


def test_every_error_entry_matches_the_pinned_grammar_c20(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    grammar = re.compile(r"^[^:]+(/[^:]+)*: \[(READ|SCHEMA|R2|R([4-9]|1[0-6]))\] .+$")
    for entry in exc_info.value.errors:
        assert grammar.match(entry), entry


def test_errors_sorted_and_deterministic_between_calls_c21(content_root):
    # Two independent problems: an unresolved entry_scene (R7) and an
    # unreferenced definition (R14) -- exercised together so sorting and
    # determinism are proved over more than one entry.
    build_version_dir(
        content_root,
        adventures={"the-sunken-mill": adventure(entry_scene="no-such-scene")},
        definitions={
            "bog-lurker": definition(),
            "unused": definition(id="unused", name="Unused Thing"),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as first:
        service.load_campaign(CAMPAIGN_ID, VERSION)
    with pytest.raises(errors.ContentInvalidError) as second:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert first.value.errors == sorted(first.value.errors)
    assert first.value.errors == second.value.errors
    assert len(first.value.errors) >= 2


def test_broken_adventure_and_broken_definition_both_reported_c22(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(
                creatures=[
                    {"definition": "no-such-thing", "count": 1},
                    {"definition": "bog-lurker", "count": 1},
                ]
            ),
        },
        definitions={"bog-lurker": definition(id="other")},
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    tags = _tags(exc_info)
    assert "R12" in tags  # mill-floor's placement of "no-such-thing"
    assert "R13" in tags  # bog-lurker.json's id no longer matches its stem


def test_malformed_campaign_json_is_exactly_one_read_entry_c23(content_root):
    version_dir = build_version_dir(content_root)
    (version_dir / "campaign.json").write_text("{not valid json")

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].startswith("campaign.json: [READ]")


def test_schema_invalid_campaign_json_is_exactly_one_schema_entry_c24(content_root):
    version_dir = build_version_dir(content_root)
    write_json(version_dir / "campaign.json", {"id": "hollow-reach"})

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].startswith("campaign.json: [SCHEMA]")


def test_model_level_schema_failure_has_no_empty_location_segment_c25(content_root):
    version_dir = build_version_dir(content_root)
    # A JSON array instead of an object: a model-level Pydantic failure whose
    # `loc` is empty.
    (version_dir / "adventures" / "the-sunken-mill.json").write_text("[]")

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    schema_entries = [e for e in exc_info.value.errors if "[SCHEMA]" in e]
    assert schema_entries
    for entry in schema_entries:
        assert ": : " not in entry


def test_broken_scene_reported_once_on_its_adventure_file_c26(content_root):
    """P1-D20: a schema-invalid inline scene is one [SCHEMA] entry on its
    *adventure* file -- never one per scene, never on a scene file, which no
    longer exists -- and the entry's detail carries Pydantic's `loc`, which
    names the scene's position (e.g. `scenes.1.truth`)."""
    build_version_dir(
        content_root,
        scenes={"mill-approach": scene_approach(), "mill-floor": scene_floor(truth=[])},
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    schema_entries = [e for e in exc_info.value.errors if "[SCHEMA]" in e]
    assert len(schema_entries) == 1
    entry = schema_entries[0]
    assert entry.startswith("adventures/the-sunken-mill.json: [SCHEMA]")
    assert "scenes" in entry
    assert "1" in entry  # mill-floor is scenes[1] in insertion order


def test_content_invalid_error_str_and_empty_errors_guard_c27():
    exc = errors.ContentInvalidError("hollow-reach", "v1", ["a: [READ] boom"])
    text = str(exc)
    assert "hollow-reach" in text
    assert "v1" in text
    assert "1" in text

    errors.ContentInvalidError("hollow-reach", "v1", [])  # must not raise


# --- The referential rules (criteria 28-42) ----------------------------------


def test_r1_missing_campaign_json_c28(content_root):
    version_dir = build_version_dir(content_root)
    (version_dir / "campaign.json").unlink()

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert len(exc_info.value.errors) == 1
    assert exc_info.value.errors[0].startswith("campaign.json: [READ]")


def test_r2_campaign_id_does_not_match_directory_name_c29(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("campaign.json: [R2]") for e in exc_info.value.errors)


def test_r4_unknown_adventure_id_c30(content_root):
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "no-such-adventure"]),
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("campaign.json: [R4]") for e in exc_info.value.errors)


def test_r4_duplicate_adventure_deduplicated_before_r8_c30(content_root):
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "the-sunken-mill"]),
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    tags = _tags(exc_info)
    assert "R4" in tags
    assert "R8" not in tags


def test_r5_orphan_adventure_file_c31(content_root):
    build_version_dir(
        content_root,
        adventures={
            "the-sunken-mill": adventure(),
            "orphan": adventure(
                id="orphan", entry_scene="mill-approach", scenes=[scene_approach()]
            ),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("adventures/orphan.json: [R5]") for e in exc_info.value.errors)


def test_r6_adventure_id_mismatch_drops_it_yielding_exactly_r6_and_r14_c32(content_root):
    """Criterion 32: setting the adventure file's `id` to a mismatch yields
    exactly two entries -- its own [R6], and an [R14] on the definition the
    dropped adventure no longer references (a dropped adventure contributes
    no scenes to R14). No third entry, and none naming a scene of that
    adventure, because the adventure is dropped from R7-R12."""
    build_version_dir(content_root, adventures={"the-sunken-mill": adventure(id="other")})

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    path_tag_pairs = {(m.group(1), m.group(2)) for m in _entries(exc_info)}
    assert path_tag_pairs == {
        ("adventures/the-sunken-mill.json", "R6"),
        ("definitions/bog-lurker.json", "R14"),
    }


def test_r7_entry_scene_not_in_adventure_scenes_c33(content_root):
    build_version_dir(
        content_root, adventures={"the-sunken-mill": adventure(entry_scene="no-such-scene")}
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("adventures/the-sunken-mill.json: [R7]") for e in exc_info.value.errors)


def test_r8_duplicate_scene_id_within_one_adventure_c34(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(id="mill-floor"),
            "mill-floor": scene_floor(),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    r8_entries = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R8"]
    assert len(r8_entries) == 1
    path, detail = r8_entries[0]
    assert path == "adventures/the-sunken-mill.json"
    assert "mill-floor" in detail
    # Companions R7 (entry scene lost) and R11 (unreachable) are expected and
    # not asserted on -- the assertion is "exactly one R8", not len == 1.
    assert len(exc_info.value.errors) > 1


def test_r8_scene_id_reused_across_two_adventures_names_the_later_one_c34(content_root):
    second_adventure = adventure(
        id="second-adventure",
        entry_scene="mill-floor",
        scenes=[scene_floor(creatures=[])],
    )
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "second-adventure"]),
        adventures={"the-sunken-mill": adventure(), "second-adventure": second_adventure},
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        m.group(1) == "adventures/second-adventure.json" and m.group(2) == "R8"
        for m in _entries(exc_info)
    )


def test_r9_exit_targets_unknown_scene_c35(content_root):
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

    r9_entries = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R9"]
    assert len(r9_entries) == 1
    path, detail = r9_entries[0]
    assert path == "adventures/the-sunken-mill.json"
    assert "mill-approach" in detail


def test_r9_exit_targets_own_scene_c35(content_root):
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

    assert any(
        m.group(1) == "adventures/the-sunken-mill.json"
        and m.group(2) == "R9"
        and "mill-approach" in m.group(3)
        for m in _entries(exc_info)
    )


def test_r9_exit_targets_scene_in_a_different_adventure_c35(content_root):
    other_scene = scene_floor(id="other-scene", creatures=[])
    other_adventure = adventure(
        id="other-adventure", entry_scene="other-scene", scenes=[other_scene]
    )
    build_version_dir(
        content_root,
        campaign=campaign(adventures=["the-sunken-mill", "other-adventure"]),
        adventures={
            "the-sunken-mill": adventure(
                scenes=[
                    scene_approach(
                        exits=[{"to": "other-scene", "description": "d", "condition": None}]
                    ),
                    scene_floor(),
                ]
            ),
            "other-adventure": other_adventure,
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        m.group(1) == "adventures/the-sunken-mill.json"
        and m.group(2) == "R9"
        and "mill-approach" in m.group(3)
        for m in _entries(exc_info)
    )


def test_r10_no_terminal_scene_c36(content_root):
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
        e.startswith("adventures/the-sunken-mill.json: [R10]") for e in exc_info.value.errors
    )


def test_r11_scene_unreachable_from_entry_scene_c37(content_root):
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(),
            "isolated": scene_floor(id="isolated", creatures=[]),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(
        e.startswith("adventures/the-sunken-mill.json: [R11]") for e in exc_info.value.errors
    )


def test_r11_scene_reachable_only_through_a_conditioned_exit_is_not_flagged_c37(content_root):
    build_version_dir(content_root)  # mill-floor is reached only via a conditioned exit

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise

    assert set(loaded.scenes.keys()) == {"mill-approach", "mill-floor"}


def test_r11_single_scene_adventure_is_not_flagged_unreachable_c37(content_root):
    single_scene_adventure = adventure(
        entry_scene="mill-approach", scenes=[scene_approach(exits=[])]
    )
    build_version_dir(
        content_root,
        adventures={"the-sunken-mill": single_scene_adventure},
        definitions={},
    )

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise

    assert list(loaded.adventures.keys()) == ["the-sunken-mill"]


def test_r12_creature_placement_targets_unknown_definition_c38(content_root):
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

    r12_entries = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R12"]
    assert len(r12_entries) == 1
    path, detail = r12_entries[0]
    assert path == "adventures/the-sunken-mill.json"
    assert "mill-floor" in detail


def test_r13_definition_id_does_not_match_filename_stem_c39(content_root):
    build_version_dir(content_root, definitions={"bog-lurker": definition(id="other")})

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("definitions/bog-lurker.json: [R13]") for e in exc_info.value.errors)


def test_r13_definition_report_and_continue_p1d19(content_root):
    """P1-D19: a definition failing R13 is not dropped -- it remains under
    its filename stem and is still evaluated by R15, e.g. a name collision
    against another definition."""
    build_version_dir(
        content_root,
        scenes={
            "mill-approach": scene_approach(),
            "mill-floor": scene_floor(
                creatures=[
                    {"definition": "bog-lurker", "count": 1},
                    {"definition": "bog-lurker-2", "count": 1},
                ]
            ),
        },
        definitions={
            "bog-lurker": definition(id="other"),
            "bog-lurker-2": definition(id="bog-lurker-2", name="Bog Lurker"),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    path_tag_pairs = {(m.group(1), m.group(2)) for m in _entries(exc_info)}
    assert ("definitions/bog-lurker.json", "R13") in path_tag_pairs
    assert ("definitions/bog-lurker-2.json", "R15") in path_tag_pairs


def test_r14_unreferenced_definition_c40(content_root):
    build_version_dir(
        content_root,
        definitions={
            "bog-lurker": definition(),
            "unused": definition(id="unused", name="Unused Thing"),
        },
    )

    with pytest.raises(errors.ContentInvalidError) as exc_info:
        service.load_campaign(CAMPAIGN_ID, VERSION)

    assert any(e.startswith("definitions/unused.json: [R14]") for e in exc_info.value.errors)


def test_r15_three_way_name_collision_case_insensitive_c41(content_root):
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
    assert ("definitions/bog-lurker-2.json", "R15") in path_tag_pairs
    assert ("definitions/bog-lurker-3.json", "R15") in path_tag_pairs
    assert ("definitions/bog-lurker.json", "R15") not in path_tag_pairs


def test_r16_definition_placed_twice_in_one_scene_c42(content_root):
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

    r16_entries = [(m.group(1), m.group(3)) for m in _entries(exc_info) if m.group(2) == "R16"]
    assert len(r16_entries) == 1
    path, detail = r16_entries[0]
    assert path == "adventures/the-sunken-mill.json"
    assert "mill-floor" in detail


def test_scenes_directory_is_ignored_entirely_c43(content_root):
    """Criterion 43: no rule polices the file layout any more. A `scenes/`
    directory placed in an otherwise-valid tree is not read, not reported,
    and the tree still loads."""
    version_dir = build_version_dir(content_root)
    (version_dir / "scenes").mkdir()
    (version_dir / "scenes" / "mill-approach.json").write_text('{"not": "even valid content"}')

    loaded = service.load_campaign(CAMPAIGN_ID, VERSION)  # must not raise

    assert set(loaded.scenes.keys()) == {"mill-approach", "mill-floor"}
