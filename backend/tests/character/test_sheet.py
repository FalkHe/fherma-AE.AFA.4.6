"""AC2, AC3 -- sprint 009-01 WI3."""

import pytest
from pydantic import ValidationError

from app.modules.character.schemas import CharacterSheet, GearRef
from app.modules.content.schemas import Abilities


def _sheet(**overrides) -> dict:
    base: dict = {
        "name": "Ilyra",
        "race": "Elf",
        "character_class": "Wizard",
        "alignment": "Chaotic Good",
        "abilities": Abilities(
            strength=10,
            dexterity=14,
            constitution=12,
            intelligence=16,
            wisdom=10,
            charisma=8,
        ),
        "max_hp": 8,
        "armour_class": 12,
        "speed": 30,
        "saving_throws": ["intelligence", "wisdom"],
        "skills": ["Arcana", "Investigation"],
        "equipment": [GearRef(kind="gear", id="spellbook")],
        "appearance": "Tall, silver-haired",
        "backstory": "A scholar of the arcane.",
    }
    base.update(overrides)
    return base


def test_ac2_a_full_character_sheet_round_trips_through_dump_and_validate():
    sheet = CharacterSheet.model_validate(_sheet())

    restored = CharacterSheet.model_validate(sheet.model_dump())

    assert restored == sheet


def test_ac3_unknown_race_class_alignment_and_skill_each_raise_validation_error():
    with pytest.raises(ValidationError):
        CharacterSheet.model_validate(_sheet(race="Klingon"))
    with pytest.raises(ValidationError):
        CharacterSheet.model_validate(_sheet(character_class="Jedi"))
    with pytest.raises(ValidationError):
        CharacterSheet.model_validate(_sheet(alignment="Neutral Evil-ish"))
    with pytest.raises(ValidationError):
        CharacterSheet.model_validate(_sheet(skills=["underwater basket weaving"]))
