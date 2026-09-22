"""AC1-AC3 -- sprint 009-02 WI1."""

import random as random_module

from app.modules.character import builder
from app.modules.character.schemas import CharacterCreateRequest
from app.modules.content.schemas import Abilities
from app.modules.playthrough import dice


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call -- the same seam and
    subclass `tests/playthrough/test_service_attack_and_damage.py` uses, so
    a roll is a known sequence rather than a real one."""

    def __init__(self, faces: list[int]) -> None:
        super().__init__()
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - scripted, bounds ignored
        return self._faces.pop(0)


def test_ac1_a_legal_spread_validates_and_an_illegal_one_names_the_problem():
    legal = builder.suggested_scores("Fighter")
    assert builder.validate_point_buy(legal) == []

    above_range = Abilities(
        strength=17, dexterity=10, constitution=10, intelligence=10, wisdom=10, charisma=10
    )
    messages = builder.validate_point_buy(above_range)
    assert any("strength" in m and "17" in m and "15" in m for m in messages)

    over_budget = Abilities(
        strength=15, dexterity=15, constitution=14, intelligence=12, wisdom=10, charisma=8
    )
    messages = builder.validate_point_buy(over_budget)
    assert any("27" in m for m in messages)


def test_ac2_roll_scores_comes_from_the_games_own_dice_and_is_reproducible(monkeypatch):
    # Four faces per ability, lowest (1) dropped -> 6+5+4 = 15 for every
    # ability; 24 values consumed in `_ABILITY_ORDER`.
    faces = [6, 5, 4, 1] * 6
    monkeypatch.setattr(dice, "_rng", lambda: _ScriptedRandom(faces))

    scores = builder.roll_scores()

    assert scores == Abilities(
        strength=15, dexterity=15, constitution=15, intelligence=15, wisdom=15, charisma=15
    )


def test_ac3_build_sheet_derives_hp_ac_saves_and_a_weapon_attack_for_a_fighter():
    request = CharacterCreateRequest(
        name="Roran",
        race="Human",
        character_class="Fighter",
        alignment="Lawful Good",
        abilities=builder.suggested_scores("Fighter"),
        equipment_picks=[0, 1, 0],  # chain mail; two martial weapons; crossbow + bolts
    )

    sheet = builder.build_sheet(request)

    con_mod = builder.modifier(sheet.abilities.constitution)
    str_mod = builder.modifier(sheet.abilities.strength)

    assert sheet.max_hp == 10 + con_mod
    assert sheet.armour_class == 16
    assert sheet.saving_throws == ["strength", "constitution"]

    longsword = next(item for item in sheet.equipment if item.id == "longsword")
    expected_damage = "1d8" if str_mod == 0 else f"1d8{str_mod:+d}"
    assert longsword.attacks[0].to_hit == 2 + str_mod
    assert longsword.attacks[0].damage == expected_damage
