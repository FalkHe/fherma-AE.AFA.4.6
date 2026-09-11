"""Tests for `app.modules.content.schemas` -- phase contract §3.

Criterion numbers refer to `step-1.1.md` §6 ("Schema", 1-10).
"""

import pytest
from pydantic import ValidationError

from app.modules.content import schemas
from tests.content.conftest import (
    abilities,
    adventure,
    campaign,
    definition,
    scene_approach,
    seed_character,
)


def test_definition_rejects_missing_stat_block_c1():
    payload = definition()
    del payload["stat_block"]
    with pytest.raises(ValidationError):
        schemas.Definition(**payload)


def test_stat_block_defaults_attacks_to_empty_list_c2():
    stat_block = definition()["stat_block"]
    del stat_block["attacks"]
    block = schemas.StatBlock(**stat_block)
    assert block.attacks == []


@pytest.mark.parametrize(
    "build",
    [
        lambda: schemas.Definition(**definition(unexpected="x")),
        lambda: schemas.Scene(**scene_approach(unexpected="x")),
        lambda: schemas.SeedCharacter(**seed_character(unexpected="x")),
    ],
)
def test_extra_key_rejected_c3(build):
    with pytest.raises(ValidationError):
        build()


def test_seed_character_rejects_class_key_instead_of_character_class_c4():
    payload = seed_character()
    payload["class"] = payload.pop("character_class")
    with pytest.raises(ValidationError):
        schemas.SeedCharacter(**payload)


def test_prose_text_rejects_blank_and_strips_surrounding_whitespace_c5():
    with pytest.raises(ValidationError):
        schemas.Scene(**scene_approach(title="   "))

    scene = schemas.Scene(**scene_approach(title="  a  "))
    assert scene.title == "a"


@pytest.mark.parametrize("bad_id", ["Mill_Floor", "mill floor", ""])
def test_content_id_rejects_non_conformant_ids_c6(bad_id):
    with pytest.raises(ValidationError):
        schemas.Definition(**definition(id=bad_id))


def test_content_id_accepts_kebab_case_c6():
    schemas.Definition(**definition(id="mill-floor"))


def test_abilities_requires_all_six_scores_c7():
    payload = abilities()
    del payload["charisma"]
    with pytest.raises(ValidationError):
        schemas.Abilities(**payload)


@pytest.mark.parametrize("bad_score", [0, 31])
def test_abilities_rejects_out_of_bounds_scores_c7(bad_score):
    with pytest.raises(ValidationError):
        schemas.Abilities(**abilities(strength=bad_score))


def test_content_model_rejects_attribute_assignment_c8():
    instance = schemas.Definition(**definition())
    with pytest.raises(ValidationError):
        instance.name = "New Name"


def test_adventure_rejects_pre_amendment_scene_id_list_c9():
    """P1-D20: `Adventure.scenes` is `list[Scene]`, not `list[ContentId]`.
    This is the one field the rework changes and the likeliest regression."""
    payload = adventure(scenes=["mill-approach", "mill-floor"])
    with pytest.raises(ValidationError):
        schemas.Adventure(**payload)


def test_adventure_rejects_scenes_objects_alongside_extra_scene_ids_key_c9():
    payload = adventure()
    payload["scene_ids"] = ["mill-approach", "mill-floor"]
    with pytest.raises(ValidationError):
        schemas.Adventure(**payload)


def test_adventure_rejects_empty_scenes_list_c10():
    with pytest.raises(ValidationError):
        schemas.Adventure(**adventure(scenes=[]))


def test_campaign_rejects_empty_adventures_list_c10():
    with pytest.raises(ValidationError):
        schemas.Campaign(**campaign(adventures=[]))
