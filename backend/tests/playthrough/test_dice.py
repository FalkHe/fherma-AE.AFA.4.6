"""WI1 (sprint 07a): dice the server rolls itself, and a formula derived
from the kind of roll and who is rolling -- AC1.

Fully engine-free: no database, no session. `roll` is exercised with
`dice._rng` monkeypatched to a fixed sequence so results are deterministic;
`derive_formula`'s content reads go through `dice.content_service`, which
tests monkeypatch to return synthetic templates rather than touching real
shipped content, so a derivation test proves the *selection* logic (by
name, never by position) rather than merely echoing greenhollow's data.
"""

from collections.abc import Iterator

import pytest

from app.modules.content.schemas import (
    Abilities,
    Attack,
    CreatureTemplate,
    ItemTemplate,
    StatBlock,
)
from app.modules.playthrough import dice
from app.modules.playthrough.models import GameObject

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"


class _FixedRandom:
    """Stands in for `random.Random`: `randint` returns the next value off
    a queue, in order, so a test can assert exact faces rather than a
    range."""

    def __init__(self, values: Iterator[int]):
        self._values = values

    def randint(self, a: int, b: int) -> int:
        return next(self._values)


_DEFAULT_ABILITIES = {
    "strength": 10,
    "dexterity": 10,
    "constitution": 10,
    "intelligence": 10,
    "wisdom": 10,
    "charisma": 10,
}


def _character(*, abilities: dict[str, int]) -> GameObject:
    return GameObject(
        campaign_run_id="run-1",
        kind="creature",
        template_id=None,
        instance_key="pc:member-1:1",
        name="Fixture Hero",
        state={"abilities": {**_DEFAULT_ABILITIES, **abilities}},
    )


def _creature(*, template_id: str = "goblin") -> GameObject:
    return GameObject(
        campaign_run_id="run-1",
        kind="creature",
        template_id=template_id,
        instance_key=f"{template_id}:1",
        name="Fixture Monster",
        state={},
    )


_ABILITIES = Abilities(
    strength=8, dexterity=14, constitution=10, intelligence=10, wisdom=7, charisma=8
)


def _goblin_template(attacks: list[Attack]) -> CreatureTemplate:
    return CreatureTemplate(
        id="goblin",
        kind="creature",
        name="Goblin",
        description="fixture",
        disposition="fixture",
        stat_block=StatBlock(
            max_hp=7, armour_class=13, abilities=_ABILITIES, attacks=attacks, traits=[]
        ),
    )


def _dagger_template(attacks: list[Attack]) -> ItemTemplate:
    return ItemTemplate(
        id="dagger", kind="item", name="Dagger", description="fixture", attacks=attacks
    )


# --- roll ------------------------------------------------------------------


def test_roll_reads_faces_and_modifier_off_the_rng_seam(monkeypatch):
    monkeypatch.setattr(dice, "_rng", lambda: _FixedRandom(iter([3, 5, 1])))

    result = dice.roll("3d6+2")

    assert result.faces == [3, 5, 1]
    assert result.modifier == 2
    assert result.total == 11


def test_roll_applies_a_negative_modifier(monkeypatch):
    monkeypatch.setattr(dice, "_rng", lambda: _FixedRandom(iter([6])))

    result = dice.roll("1d20-3")

    assert result.faces == [6]
    assert result.modifier == -3
    assert result.total == 3


def test_roll_defaults_the_modifier_to_zero_when_absent(monkeypatch):
    monkeypatch.setattr(dice, "_rng", lambda: _FixedRandom(iter([4, 4])))

    result = dice.roll("2d8")

    assert result.modifier == 0
    assert result.total == 8


@pytest.mark.parametrize("expression", ["", "d6", "2d", "2x6", "2d6+", "six dice", "2d6*2"])
def test_roll_names_a_malformed_expression_in_its_own_error(expression):
    with pytest.raises(dice.InvalidDiceExpressionError) as excinfo:
        dice.roll(expression)

    assert excinfo.value.expression == expression


def test_roll_refuses_more_dice_than_the_cap():
    with pytest.raises(dice.InvalidDiceExpressionError) as excinfo:
        dice.roll("21d6")

    assert excinfo.value.expression == "21d6"


def test_roll_refuses_more_faces_than_the_cap():
    with pytest.raises(dice.InvalidDiceExpressionError) as excinfo:
        dice.roll("1d101")

    assert excinfo.value.expression == "1d101"


def test_roll_accepts_the_cap_itself(monkeypatch):
    monkeypatch.setattr(dice, "_rng", lambda: _FixedRandom(iter([1] * 20)))

    result = dice.roll("20d100")

    assert len(result.faces) == 20
    assert result.total == 20


# --- derive_formula: attack / damage ---------------------------------------


def test_derive_formula_attack_from_an_item_template(monkeypatch):
    monkeypatch.setattr(
        dice.content_service,
        "load_object_template",
        lambda campaign_id, version, template_id: _dagger_template(
            [Attack(name="Dagger", to_hit=5, damage="1d4+3")]
        ),
    )
    actor = _character(abilities={"strength": 10, "dexterity": 20})

    formula = dice.derive_formula(
        "attack", actor, {"item_id": "dagger"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )

    assert formula == "1d20+5"


def test_derive_formula_damage_from_an_item_template(monkeypatch):
    monkeypatch.setattr(
        dice.content_service,
        "load_object_template",
        lambda campaign_id, version, template_id: _dagger_template(
            [Attack(name="Dagger", to_hit=5, damage="1d4+3")]
        ),
    )
    actor = _character(abilities={"strength": 10, "dexterity": 20})

    formula = dice.derive_formula(
        "damage", actor, {"item_id": "dagger"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )

    assert formula == "1d4+3"


def test_derive_formula_attack_from_a_monster_stat_block_is_chosen_by_name_not_position(
    monkeypatch,
):
    # The wanted attack ("Sling") is deliberately *not* first in the list --
    # a position-based pick (`attacks[0]`) would silently return the sword.
    monkeypatch.setattr(
        dice.content_service,
        "load_object_template",
        lambda campaign_id, version, template_id: _goblin_template(
            [
                Attack(name="Rusty Shortsword", to_hit=4, damage="1d6+2"),
                Attack(name="Sling", to_hit=2, damage="1d4+2"),
            ]
        ),
    )
    actor = _creature()

    to_hit = dice.derive_formula(
        "attack", actor, {"attack": "Sling"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )
    damage = dice.derive_formula(
        "damage", actor, {"attack": "Sling"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )

    assert to_hit == "1d20+2"
    assert damage == "1d4+2"


def test_derive_formula_attack_from_a_monster_with_one_attack_needs_no_name(monkeypatch):
    monkeypatch.setattr(
        dice.content_service,
        "load_object_template",
        lambda campaign_id, version, template_id: _goblin_template(
            [Attack(name="Claw", to_hit=3, damage="1d4+1")]
        ),
    )
    actor = _creature()

    formula = dice.derive_formula("attack", actor, {}, campaign_id=CAMPAIGN_ID, version=VERSION)

    assert formula == "1d20+3"


def test_derive_formula_attack_from_a_monster_with_several_requires_the_name(monkeypatch):
    monkeypatch.setattr(
        dice.content_service,
        "load_object_template",
        lambda campaign_id, version, template_id: _goblin_template(
            [
                Attack(name="Rusty Shortsword", to_hit=4, damage="1d6+2"),
                Attack(name="Sling", to_hit=2, damage="1d4+2"),
            ]
        ),
    )
    actor = _creature()

    with pytest.raises(ValueError):
        dice.derive_formula("attack", actor, {}, campaign_id=CAMPAIGN_ID, version=VERSION)


# --- derive_formula: ability_check / saving_throw / initiative -------------


def test_derive_formula_ability_check_uses_the_named_ability_modifier():
    actor = _character(abilities={"strength": 16, "dexterity": 10})

    formula = dice.derive_formula(
        "ability_check",
        actor,
        {"ability": "strength"},
        campaign_id=CAMPAIGN_ID,
        version=VERSION,
    )

    assert formula == "1d20+3"


def test_derive_formula_saving_throw_uses_the_named_ability_modifier():
    actor = _character(abilities={"strength": 10, "dexterity": 10, "wisdom": 7})

    formula = dice.derive_formula(
        "saving_throw",
        actor,
        {"ability": "wisdom"},
        campaign_id=CAMPAIGN_ID,
        version=VERSION,
    )

    assert formula == "1d20-2"


def test_derive_formula_ability_modifier_floors_toward_negative_infinity():
    # (7 - 10) // 2 == -2, not -1 -- floor division, per the SRD (D6).
    actor = _character(abilities={"strength": 7})

    formula = dice.derive_formula(
        "ability_check",
        actor,
        {"ability": "strength"},
        campaign_id=CAMPAIGN_ID,
        version=VERSION,
    )

    assert formula == "1d20-2"


def test_derive_formula_ability_check_omits_the_sign_for_a_zero_modifier():
    actor = _character(abilities={"strength": 10})

    formula = dice.derive_formula(
        "ability_check",
        actor,
        {"ability": "strength"},
        campaign_id=CAMPAIGN_ID,
        version=VERSION,
    )

    assert formula == "1d20"


def test_derive_formula_initiative_uses_dexterity_regardless_of_context():
    actor = _character(abilities={"strength": 20, "dexterity": 16})

    formula = dice.derive_formula("initiative", actor, {}, campaign_id=CAMPAIGN_ID, version=VERSION)

    assert formula == "1d20+3"


def test_derive_formula_initiative_from_a_monster_stat_block(monkeypatch):
    monkeypatch.setattr(
        dice.content_service,
        "load_object_template",
        lambda campaign_id, version, template_id: _goblin_template([]),
    )
    actor = _creature()

    formula = dice.derive_formula("initiative", actor, {}, campaign_id=CAMPAIGN_ID, version=VERSION)

    # _ABILITIES.dexterity == 14 -> modifier +2
    assert formula == "1d20+2"


# --- derive_formula: custom --------------------------------------------------


def test_derive_formula_custom_returns_the_explicit_expression_verbatim():
    actor = _character(abilities={"strength": 10})

    formula = dice.derive_formula(
        "custom",
        actor,
        {"expression": "4d4"},
        campaign_id=CAMPAIGN_ID,
        version=VERSION,
    )

    assert formula == "4d4"
