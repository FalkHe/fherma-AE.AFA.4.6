"""The level-1 character sheet shape and the SRD 5.1 option types it is
built from -- races, classes, skills, alignments, armour, weapons and gear.

`options.py` (WI1) and `classes.py` (WI2) instantiate these as hand-authored
Python literals; nothing here loads or parses anything (module README's
"content lives in git" approach, same as `app.modules.content`)."""

from typing import Literal

from pydantic import ConfigDict, Field

from app.core.schemas import CamelModel
from app.modules.content.schemas import Abilities, Attack

Ability = Literal["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]

SkillName = Literal[
    "Acrobatics",
    "Animal Handling",
    "Arcana",
    "Athletics",
    "Deception",
    "History",
    "Insight",
    "Intimidation",
    "Investigation",
    "Medicine",
    "Nature",
    "Perception",
    "Performance",
    "Persuasion",
    "Religion",
    "Sleight of Hand",
    "Stealth",
    "Survival",
]

RaceName = Literal[
    "Dragonborn",
    "Dwarf",
    "Elf",
    "Gnome",
    "Half-Elf",
    "Half-Orc",
    "Halfling",
    "Human",
    "Tiefling",
]

ClassName = Literal[
    "Barbarian",
    "Bard",
    "Cleric",
    "Druid",
    "Fighter",
    "Monk",
    "Paladin",
    "Ranger",
    "Rogue",
    "Sorcerer",
    "Warlock",
    "Wizard",
]

AlignmentName = Literal[
    "Lawful Good",
    "Neutral Good",
    "Chaotic Good",
    "Lawful Neutral",
    "Neutral",
    "Chaotic Neutral",
    "Lawful Evil",
    "Neutral Evil",
    "Chaotic Evil",
]

DamageType = Literal["bludgeoning", "piercing", "slashing"]

GearKind = Literal["armour", "weapon", "gear", "pack", "weapon_category"]


class SrdContent(CamelModel):
    """Base for the hand-authored SRD reference data in `options.py` /
    `classes.py`: immutable, no unexpected fields -- same intent as
    `content.schemas.ContentModel`, on top of `CamelModel` since this data
    is also served over the wire."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Skill(SrdContent):
    name: SkillName
    ability: Ability


class Race(SrdContent):
    name: RaceName
    ability_bonuses: dict[Ability, int]
    free_ability_bonuses: int = 0
    speed: int
    size: Literal["Small", "Medium"]


class Alignment(SrdContent):
    name: AlignmentName
    abbreviation: str


class Armour(SrdContent):
    id: str
    name: str
    category: Literal["light", "medium", "heavy", "shield"]
    base_ac: int
    dex_bonus: Literal["full", "max2", "none"]
    strength_requirement: int | None
    stealth_disadvantage: bool


class Weapon(SrdContent):
    id: str
    name: str
    proficiency: Literal["simple", "martial"]
    ranged: bool
    damage_die: str
    damage_type: DamageType
    finesse: bool
    two_handed: bool
    versatile_die: str | None


class GearItem(SrdContent):
    id: str
    name: str
    description: str = ""


class GearRef(SrdContent):
    kind: GearKind
    id: str
    quantity: int = Field(default=1, ge=1)


class SheetItem(GearRef):
    """A resolved piece of a finished sheet's equipment -- a `GearRef` with
    its display name and, for a weapon, its derived attack(s) already
    worked out, so `playthrough.create_character` can write it straight
    into a carried row's state without calling back into this module."""

    name: str
    attacks: list[Attack] = []


class EquipmentOption(SrdContent):
    label: str
    items: list[GearRef]


class EquipmentChoice(SrdContent):
    """One equipment line a player picks from; `options[0]` is the
    default when a player does not choose."""

    options: list[EquipmentOption] = Field(min_length=1)


class CharacterClass(SrdContent):
    name: ClassName
    hit_die: int
    saving_throws: list[Ability]
    skill_choices: int
    skill_options: list[SkillName]
    armour_proficiencies: list[str]
    weapon_proficiencies: list[str]
    equipment: list[EquipmentChoice]


class PointBuy(SrdContent):
    costs: dict[int, int]
    budget: int
    minimum: int
    maximum: int


class CharacterSheet(CamelModel):
    """A finished level-1 character, as created by a player -- not static
    SRD content, so plain `CamelModel` rather than `SrdContent`."""

    name: str
    race: RaceName
    character_class: ClassName
    level: Literal[1] = 1
    alignment: AlignmentName
    abilities: Abilities
    max_hp: int = Field(ge=1)
    armour_class: int = Field(ge=1)
    speed: int = Field(ge=0)
    saving_throws: list[Ability]
    skills: list[SkillName]
    equipment: list[SheetItem]
    proficiency_bonus: int = 2
    appearance: str
    backstory: str


class CharacterCreateRequest(CamelModel):
    """What a player submits to build a level-1 character; `builder.py`
    turns this into a `CharacterSheet` (validating and deriving everything
    the caller must not hand in directly)."""

    name: str
    race: RaceName
    character_class: ClassName
    alignment: AlignmentName
    abilities: Abilities
    free_ability_bonuses: list[Ability] = []
    skills: list[SkillName] = []
    equipment_picks: list[int] = []
    appearance: str = ""
    backstory: str = ""


CreationStepName = Literal[
    "raceClass", "scores", "identity", "skills", "alignment", "equipment", "review"
]


class SheetSoFar(CamelModel):
    """The draft as it stands, on the wire (sprint 009-05, WI1): every
    field nullable, filled in only as the conversation settles it.
    `maxHp`, `armourClass`, `speed`, `skills` and `equipment` only ever
    come from a successful `service.build_sheet` -- everything else is
    read straight off the draft (← research Decision 3)."""

    name: str | None = None
    race: RaceName | None = None
    character_class: ClassName | None = None
    level: Literal[1] | None = None
    alignment: AlignmentName | None = None
    abilities: Abilities | None = None
    max_hp: int | None = None
    armour_class: int | None = None
    speed: int | None = None
    skills: list[SkillName] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    appearance: str | None = None
    backstory: str | None = None


class SendCreationMessageRequest(CamelModel):
    text: str = Field(min_length=1)


class CreationReply(CamelModel):
    """Both creation-chat routes answer this (sprint 009-05, WI1): the
    Keeper's words plus everything the sheet-so-far panel needs, so the
    page never makes a second read (← AC3)."""

    conversation_id: str
    reply: str
    sheet: SheetSoFar
    step: CreationStepName
    step_number: int = Field(ge=1, le=7)
    can_save: bool
    saved: bool
    error: bool
    ready_made_name: str | None = None
