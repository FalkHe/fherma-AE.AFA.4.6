"""Pure functions that turn a player's choices into a finished level-1
character sheet: point buy, a suggested set per class, scores rolled
through the game's own dice, racial bonuses, modifiers, hit points, armour
class, saving throws and each weapon's to-hit and damage.

No session, no I/O of its own -- the only entropy is `playthrough.dice`'s
seam (← D5): the game rolls, a caller never supplies a number. `build_sheet`
is the one entry a caller needs; every other function is a building block
it (or a future caller) composes."""

from app.modules.content.schemas import Abilities, Attack
from app.modules.playthrough import dice

from . import service
from .errors import CharacterBuildError
from .options import ARMOURS, GEAR, POINT_BUY, WEAPONS
from .schemas import (
    Ability,
    Armour,
    CharacterClass,
    CharacterCreateRequest,
    CharacterSheet,
    ClassName,
    GearRef,
    Race,
    SheetItem,
    Weapon,
)

_WEAPONS_BY_ID: dict[str, Weapon] = {weapon.id: weapon for weapon in WEAPONS}
_ARMOURS_BY_ID: dict[str, Armour] = {armour.id: armour for armour in ARMOURS}
_GEAR_BY_ID = {item.id: item for item in GEAR}

# A `weapon_category` pick (brief WI1 ← Decision 2) always resolves to a
# real item -- a named pick is out of scope for this sprint.
_WEAPON_CATEGORY_DEFAULTS = {
    "simple": "mace",
    "simple_melee": "mace",
    "martial": "longsword",
    "martial_melee": "longsword",
}

_ABILITY_ORDER: tuple[Ability, ...] = (
    "strength",
    "dexterity",
    "constitution",
    "intelligence",
    "wisdom",
    "charisma",
)

_SUGGESTED_SCORES = (15, 14, 13, 12, 10, 8)

# Hand-authored per-class ability priority, highest suggested score first;
# always spends the full 27-point budget (9+7+5+4+2+0).
_CLASS_ABILITY_PRIORITY: dict[ClassName, tuple[Ability, ...]] = {
    "Barbarian": ("strength", "constitution", "dexterity", "wisdom", "charisma", "intelligence"),
    "Bard": ("charisma", "dexterity", "constitution", "wisdom", "intelligence", "strength"),
    "Cleric": ("wisdom", "constitution", "strength", "charisma", "dexterity", "intelligence"),
    "Druid": ("wisdom", "constitution", "dexterity", "intelligence", "charisma", "strength"),
    "Fighter": ("strength", "constitution", "dexterity", "wisdom", "intelligence", "charisma"),
    "Monk": ("dexterity", "wisdom", "constitution", "strength", "intelligence", "charisma"),
    "Paladin": ("strength", "charisma", "constitution", "wisdom", "dexterity", "intelligence"),
    "Ranger": ("dexterity", "wisdom", "constitution", "strength", "intelligence", "charisma"),
    "Rogue": ("dexterity", "intelligence", "constitution", "wisdom", "charisma", "strength"),
    "Sorcerer": ("charisma", "constitution", "dexterity", "wisdom", "intelligence", "strength"),
    "Warlock": ("charisma", "constitution", "dexterity", "wisdom", "intelligence", "strength"),
    "Wizard": ("intelligence", "dexterity", "constitution", "wisdom", "charisma", "strength"),
}


def point_buy_cost(scores: Abilities) -> int:
    costs = POINT_BUY.costs
    return sum(costs[value] for value in scores.model_dump().values() if value in costs)


def validate_point_buy(scores: Abilities) -> list[str]:
    """`[]` when `scores` is a legal 27-point spread; otherwise one message
    per problem -- an ability outside 8..15, or (only once every ability is
    in range) the total spending more than the budget."""
    messages: list[str] = []
    for ability, value in scores.model_dump().items():
        if value < POINT_BUY.minimum:
            messages.append(f"{ability} {value} is below {POINT_BUY.minimum}")
        elif value > POINT_BUY.maximum:
            messages.append(f"{ability} {value} is above {POINT_BUY.maximum}")

    if not messages:
        cost = point_buy_cost(scores)
        if cost > POINT_BUY.budget:
            messages.append(f"spread costs {cost} of {POINT_BUY.budget} points")

    return messages


def suggested_scores(class_name: ClassName) -> Abilities:
    priority = _CLASS_ABILITY_PRIORITY[class_name]
    return Abilities.model_validate(dict(zip(priority, _SUGGESTED_SCORES, strict=True)))


def roll_scores() -> Abilities:
    """Six 4d6-drop-lowest rolls, one per ability in `_ABILITY_ORDER`,
    through `dice.roll` -- never a caller-supplied number (← D5)."""
    values: dict[str, int] = {}
    for ability in _ABILITY_ORDER:
        faces = sorted(dice.roll("4d6").faces)
        values[ability] = sum(faces[1:])
    return Abilities.model_validate(values)


def apply_race(scores: Abilities, race: Race, free: list[Ability]) -> Abilities:
    """`race.ability_bonuses` applied outright, plus one point each to
    `free` abilities (Half-Elf's two free +1s) -- or, when `free` is empty,
    to the two highest abilities the race did not already bonus."""
    values = scores.model_dump()
    for ability, bonus in race.ability_bonuses.items():
        values[ability] += bonus

    count = race.free_ability_bonuses
    if count:
        chosen = list(free[:count])
        if not chosen:
            others = [ability for ability in _ABILITY_ORDER if ability not in race.ability_bonuses]
            others.sort(key=lambda ability: values[ability], reverse=True)
            chosen = others[:count]
        for ability in chosen:
            values[ability] += 1

    return Abilities.model_validate(values)


def modifier(score: int) -> int:
    return dice._ability_modifier(score)  # noqa: SLF001 -- the one seam, per the brief


def derive_hp(cls: CharacterClass, con_mod: int) -> int:
    return max(1, cls.hit_die + con_mod)


def derive_ac(dex_mod: int, armour: Armour | None, shield: bool) -> int:
    if armour is None:
        ac = 10 + dex_mod
    elif armour.dex_bonus == "full":
        ac = armour.base_ac + dex_mod
    elif armour.dex_bonus == "max2":
        ac = armour.base_ac + min(dex_mod, 2)
    else:
        ac = armour.base_ac
    if shield:
        ac += 2
    return ac


def derive_saves(cls: CharacterClass) -> list[Ability]:
    return list(cls.saving_throws)


def _attack_modifier(weapon: Weapon, scores: Abilities) -> int:
    if weapon.ranged:
        return modifier(scores.dexterity)
    if weapon.finesse:
        return max(modifier(scores.strength), modifier(scores.dexterity))
    return modifier(scores.strength)


def weapon_attack(w: Weapon, scores: Abilities, proficient: bool) -> Attack:
    mod = _attack_modifier(w, scores)
    to_hit = (2 if proficient else 0) + mod
    damage = w.damage_die if mod == 0 else f"{w.damage_die}{mod:+d}"
    return Attack(name=w.name, to_hit=to_hit, damage=damage)


def _resolve_gear_ref(ref: GearRef, scores: Abilities) -> SheetItem:
    if ref.kind == "weapon_category":
        weapon = _WEAPONS_BY_ID[_WEAPON_CATEGORY_DEFAULTS[ref.id]]
        return SheetItem(
            kind="weapon",
            id=weapon.id,
            quantity=ref.quantity,
            name=weapon.name,
            attacks=[weapon_attack(weapon, scores, proficient=True)],
        )
    if ref.kind == "weapon":
        weapon = _WEAPONS_BY_ID[ref.id]
        return SheetItem(
            kind="weapon",
            id=weapon.id,
            quantity=ref.quantity,
            name=weapon.name,
            attacks=[weapon_attack(weapon, scores, proficient=True)],
        )
    if ref.kind == "armour":
        armour = _ARMOURS_BY_ID[ref.id]
        return SheetItem(kind="armour", id=armour.id, quantity=ref.quantity, name=armour.name)
    item = _GEAR_BY_ID[ref.id]
    return SheetItem(kind=ref.kind, id=item.id, quantity=ref.quantity, name=item.name)


def resolve_equipment(cls: CharacterClass, scores: Abilities, picks: list[int]) -> list[SheetItem]:
    """One option index per class equipment choice (short or empty picks
    default to 0, ← the brief); starting gear is proficient by definition,
    so every resolved weapon carries its attack already."""
    items: list[SheetItem] = []
    for index, choice in enumerate(cls.equipment):
        pick = picks[index] if index < len(picks) else 0
        if not (0 <= pick < len(choice.options)):
            raise CharacterBuildError([f"equipment choice {index} has no option {pick}"])
        for ref in choice.options[pick].items:
            items.append(_resolve_gear_ref(ref, scores))
    return items


def build_sheet(request: CharacterCreateRequest) -> CharacterSheet:
    """The one entry: validate the point-buy spread, apply the race, derive
    everything else, and assemble the finished sheet. Raises
    `CharacterBuildError` on an illegal spread or an unknown equipment pick
    -- never on anything a caller could not have avoided."""
    messages = validate_point_buy(request.abilities)
    if messages:
        raise CharacterBuildError(messages)

    race = service.race(request.race)
    character_class = service.character_class(request.character_class)

    scores = apply_race(request.abilities, race, request.free_ability_bonuses)
    equipment = resolve_equipment(character_class, scores, request.equipment_picks)

    shield = any(item.kind == "armour" and item.id == "shield" for item in equipment)
    worn = next((item for item in equipment if item.kind == "armour" and item.id != "shield"), None)
    armour = _ARMOURS_BY_ID[worn.id] if worn is not None else None

    con_mod = modifier(scores.constitution)
    dex_mod = modifier(scores.dexterity)

    return CharacterSheet(
        name=request.name,
        race=request.race,
        character_class=request.character_class,
        alignment=request.alignment,
        abilities=scores,
        max_hp=derive_hp(character_class, con_mod),
        armour_class=derive_ac(dex_mod, armour, shield),
        speed=race.speed,
        saving_throws=derive_saves(character_class),
        skills=request.skills,
        equipment=equipment,
        appearance=request.appearance,
        backstory=request.backstory,
    )
