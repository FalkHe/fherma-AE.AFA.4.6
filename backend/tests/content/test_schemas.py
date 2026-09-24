"""Tests for `app.modules.content.schemas` -- step-1.4.md §3 (`ObjectTemplate`,
`FixtureCheck`, `Placement`, `Carried`) and the models it leaves unchanged.

Criterion numbers refer to `step-1.4.md` §10 ("The schema", 1-12).
"""

import pytest
from pydantic import ValidationError

from app.modules.content import schemas
from tests.content.conftest import (
    abilities,
    adventure,
    campaign,
    creature_template,
    fixture_template,
    item_template,
    scene_approach,
    seed_character,
)

# --- 1: CreatureTemplate -----------------------------------------------------


def test_creature_template_loads_with_expected_fields_c1():
    template = schemas.CreatureTemplate(**creature_template())
    assert isinstance(template, schemas.CreatureTemplate)
    assert template.kind == "creature"


def test_object_template_union_discriminates_creature_c1():
    # ObjectTemplate is a type alias (Annotated Union), not itself callable in
    # the way a class is -- so it is exercised through a model that holds it.
    template = schemas.Campaign(**campaign()).object_templates[0]
    assert isinstance(template, schemas.CreatureTemplate)
    assert template.kind == "creature"


# --- 2: ItemTemplate ----------------------------------------------------------


def test_item_template_loads_c2():
    template = schemas.ItemTemplate(
        **item_template(attacks=[{"name": "Shiv", "to_hit": 3, "damage": "1d4"}])
    )
    assert isinstance(template, schemas.ItemTemplate)
    assert len(template.attacks) == 1


def test_item_template_omitting_attacks_defaults_to_empty_list_c2():
    payload = item_template()
    del payload["attacks"]
    template = schemas.ItemTemplate(**payload)
    assert template.attacks == []


# --- 3, 3a: FixtureTemplate / FixtureCheck.bypassed_by -----------------------


def test_fixture_template_with_one_check_loads_c3():
    template = schemas.FixtureTemplate(**fixture_template(checks=[fixture_template()["checks"][0]]))
    assert isinstance(template, schemas.FixtureTemplate)
    assert template.checks[0].bypassed_by == []


def test_fixture_check_explicit_empty_bypassed_by_equals_absent_key_c3():
    payload = fixture_template()["checks"][0]
    assert "bypassed_by" not in payload
    without_key = schemas.FixtureCheck(**payload)

    with_empty_list = schemas.FixtureCheck(**payload, bypassed_by=[])

    assert without_key.bypassed_by == [] == with_empty_list.bypassed_by


def test_bypassed_by_is_a_list_in_declared_order_c3a():
    check = schemas.FixtureCheck(
        action="Cut the lashings",
        ability="strength",
        dc=10,
        success="It opens.",
        bypassed_by=["shepherds-knife", "notched-cleaver"],
    )
    assert check.bypassed_by == ["shepherds-knife", "notched-cleaver"]

    single = schemas.FixtureCheck(
        action="Cut the lashings",
        ability="strength",
        dc=10,
        success="It opens.",
        bypassed_by=["shepherds-knife"],
    )
    assert single.bypassed_by == ["shepherds-knife"]


@pytest.mark.parametrize(
    "bypassed_by",
    [
        "shepherds-knife",  # bare scalar string, the old form
        None,
        ["Shepherds Knife"],  # not a ContentId
    ],
)
def test_bypassed_by_rejects_non_list_and_non_id_forms_c3a(bypassed_by):
    with pytest.raises(ValidationError):
        schemas.FixtureCheck(
            action="Cut the lashings",
            ability="strength",
            dc=10,
            success="It opens.",
            bypassed_by=bypassed_by,
        )


# --- 4: wrong-kind fields rejected -------------------------------------------


def test_item_template_rejects_stat_block_c4():
    with pytest.raises(ValidationError):
        schemas.ItemTemplate(**item_template(stat_block=creature_template()["stat_block"]))


def test_item_template_rejects_disposition_c4():
    with pytest.raises(ValidationError):
        schemas.ItemTemplate(**item_template(disposition="wants nothing"))


def test_creature_template_rejects_checks_c4():
    with pytest.raises(ValidationError):
        schemas.CreatureTemplate(**creature_template(checks=fixture_template()["checks"]))


def test_fixture_template_rejects_attacks_c4():
    with pytest.raises(ValidationError):
        schemas.FixtureTemplate(**fixture_template(attacks=[]))


def test_creature_template_rejects_top_level_attacks_c4():
    with pytest.raises(ValidationError):
        schemas.CreatureTemplate(**creature_template(attacks=[]))


# --- 5: discriminator failures ------------------------------------------------


def test_object_template_with_no_kind_fails_c5():
    payload = creature_template()
    del payload["kind"]
    with pytest.raises(ValidationError):
        schemas.Campaign(**campaign(object_templates=[payload]))


def test_object_template_with_unknown_kind_fails_c5():
    with pytest.raises(ValidationError):
        schemas.Campaign(**campaign(object_templates=[creature_template(kind="creatures")]))


# --- 6: FixtureTemplate.checks min_length=1 -----------------------------------


def test_fixture_template_rejects_empty_checks_c6():
    with pytest.raises(ValidationError):
        schemas.FixtureTemplate(**fixture_template(checks=[]))


def test_fixture_template_rejects_missing_checks_key_c6():
    payload = fixture_template()
    del payload["checks"]
    with pytest.raises(ValidationError):
        schemas.FixtureTemplate(**payload)


# --- 7: FixtureCheck.dc bounds -------------------------------------------------


@pytest.mark.parametrize("bad_dc", [4, 31])
def test_fixture_check_dc_out_of_bounds_rejected_c7(bad_dc):
    with pytest.raises(ValidationError):
        schemas.FixtureCheck(action="do it", ability="strength", dc=bad_dc, success="it happens")


@pytest.mark.parametrize("good_dc", [5, 30])
def test_fixture_check_dc_bounds_accepted_c7(good_dc):
    check = schemas.FixtureCheck(
        action="do it", ability="strength", dc=good_dc, success="it happens"
    )
    assert check.dc == good_dc


def test_fixture_check_missing_ability_rejected_ac1():
    with pytest.raises(ValidationError):
        schemas.FixtureCheck(action="do it", dc=10, success="it happens")


# --- AC5: the SRD's difficulty floor -- FixtureCheck.dc and Secret.dc ----------


@pytest.mark.parametrize("bad_dc", [4, 31])
def test_secret_dc_out_of_bounds_rejected_ac5(bad_dc):
    with pytest.raises(ValidationError):
        schemas.Secret(fact="A hidden latch", ability="wisdom", dc=bad_dc, discovered_by="a search")


@pytest.mark.parametrize("good_dc", [5, 30])
def test_secret_dc_bounds_accepted_ac5(good_dc):
    secret = schemas.Secret(
        fact="A hidden latch", ability="wisdom", dc=good_dc, discovered_by="a search"
    )
    assert secret.dc == good_dc


def test_secret_missing_ability_rejected_ac1():
    with pytest.raises(ValidationError):
        schemas.Secret(fact="A hidden latch", dc=10, discovered_by="a search")


# --- 8: Carried is not recursive -----------------------------------------------


def test_carried_rejects_nested_carries_c8():
    with pytest.raises(ValidationError):
        schemas.Carried(template="rusty-key", count=1, carries=[])


# --- 9: Placement.count ---------------------------------------------------------


def test_placement_rejects_count_zero_c9():
    with pytest.raises(ValidationError):
        schemas.Placement(template="bog-lurker", count=0)


def test_placement_defaults_count_and_carries_c9():
    placement = schemas.Placement(template="bog-lurker")
    assert placement.count == 1
    assert placement.carries == []


# --- 10: no compatibility alias for the old keys -------------------------------


def test_scene_rejects_old_creatures_key_c10():
    payload = scene_approach()
    payload["creatures"] = []
    with pytest.raises(ValidationError):
        schemas.Scene(**payload)


def test_placement_rejects_old_definition_key_c10():
    with pytest.raises(ValidationError):
        schemas.Placement(definition="bog-lurker", count=1)


# --- 11: Campaign.object_templates min_length=1 --------------------------------


def test_campaign_rejects_empty_object_templates_c11():
    with pytest.raises(ValidationError):
        schemas.Campaign(**campaign(object_templates=[]))


# --- 12: SeedCharacter.inventory is a list of content ids (AC3, I2) ------------


def test_seed_character_inventory_is_list_of_content_ids_c12():
    character = schemas.SeedCharacter(**seed_character())
    assert character.inventory == ["rusty-key"]


def test_seed_character_inventory_defaults_to_empty_list_c12():
    payload = seed_character()
    del payload["inventory"]
    character = schemas.SeedCharacter(**payload)
    assert character.inventory == []


def test_seed_character_inventory_rejects_non_content_id_entries_c12():
    with pytest.raises(ValidationError):
        schemas.SeedCharacter(**seed_character(inventory=["a shortsword"]))


# --- AC1: Exit gains id and kind; `to` follows kind (I1) ------------------------


def _exit(**overrides) -> dict:
    payload = {
        "id": "into-the-mill",
        "to": "mill-floor",
        "description": "The mill door, barred from within.",
    }
    payload.update(overrides)
    return payload


def test_exit_defaults_to_kind_scene_ac1():
    exit_ = schemas.Exit(**_exit())
    assert exit_.kind == "scene"
    assert exit_.to == "mill-floor"


def test_exit_scene_without_to_is_rejected_ac1():
    payload = _exit()
    del payload["to"]
    with pytest.raises(ValidationError):
        schemas.Exit(**payload)


def test_exit_adventure_end_without_to_is_valid_ac1():
    exit_ = schemas.Exit(id="out-of-the-mill", kind="adventure_end", description="Freedom.")
    assert exit_.to is None


def test_exit_adventure_end_with_to_is_rejected_ac1():
    with pytest.raises(ValidationError):
        schemas.Exit(**_exit(kind="adventure_end"))


def test_exit_requires_id_ac1():
    payload = _exit()
    del payload["id"]
    with pytest.raises(ValidationError):
        schemas.Exit(**payload)


# --- carried-over schema conventions (unchanged models, still worth a smoke test) --


def test_content_model_rejects_attribute_assignment():
    instance = schemas.CreatureTemplate(**creature_template())
    with pytest.raises(ValidationError):
        instance.name = "New Name"


def test_prose_text_rejects_blank_and_strips_surrounding_whitespace():
    with pytest.raises(ValidationError):
        schemas.Scene(**scene_approach(title="   "))
    scene = schemas.Scene(**scene_approach(title="  a  "))
    assert scene.title == "a"


@pytest.mark.parametrize("bad_id", ["Mill_Floor", "mill floor", ""])
def test_content_id_rejects_non_conformant_ids(bad_id):
    with pytest.raises(ValidationError):
        schemas.CreatureTemplate(**creature_template(id=bad_id))


def test_abilities_requires_all_six_scores():
    payload = abilities()
    del payload["charisma"]
    with pytest.raises(ValidationError):
        schemas.Abilities(**payload)


def test_adventure_rejects_pre_amendment_scene_id_list():
    payload = adventure(scenes=["mill-approach", "mill-floor"])
    with pytest.raises(ValidationError):
        schemas.Adventure(**payload)
