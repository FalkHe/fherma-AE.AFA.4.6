---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 01

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | `character/schemas.py` (every type of I1) and `character/options.py`: races, skills, alignments, armour, weapons, gear/packs, point-buy literals from the SRD anchors | none of its own (WI3 tests it) | – |
| 2 | backend-python | `character/classes.py`: the twelve `CharacterClass` literals from the SRD anchors, equipment as `list[EquipmentChoice]` | none of its own (WI3 tests it) | I1 |
| 3 | backend-python | `character/service.py`, `character/commands.py` (`app character options`), one line in `app/cli.py`, `character/README.md` (names point buy as our own rule), `backend/tests/character/` | AC1 counts 9/12/18/9 · AC2 full sheet round-trips · AC3 unknown race/class/alignment/skill refused · AC4 readers take no argument · AC5/Outcome: command exits 0 and prints Barbarian d12, saves, greataxe line | I1, I2 |

No qa work item: the backlog reserves black-box tests for sprint 05; WI3's tests are the sprint's tests, one per criterion.

## Interfaces
I1 = `schemas.py` and `service.py` shapes, I2 = the `classes.py` literal `CLASSES: list[CharacterClass]` and `options.py` literals `RACES, SKILLS, ALIGNMENTS, ARMOURS, WEAPONS, GEAR, POINT_BUY`, all verbatim from research:

`schemas.py` (WI1), all `CamelModel` from `app.core.schemas`:

```
Ability      = Literal["strength",...,"charisma"]
SkillName    = Literal[<18>]   RaceName = Literal[<9>]   ClassName = Literal[<12>]
AlignmentName = Literal[<9>]   DamageType = Literal["bludgeoning","piercing","slashing"]
GearKind     = Literal["armour","weapon","gear","pack","weapon_category"]

Skill(name: SkillName, ability: Ability)
Race(name: RaceName, ability_bonuses: dict[Ability,int], free_ability_bonuses: int = 0,
     speed: int, size: Literal["Small","Medium"])          # Half-Elf: free_ability_bonuses=2
Alignment(name: AlignmentName, abbreviation: str)
Armour(id: str, name: str, category: Literal["light","medium","heavy","shield"], base_ac: int,
       dex_bonus: Literal["full","max2","none"], strength_requirement: int | None,
       stealth_disadvantage: bool)
Weapon(id: str, name: str, proficiency: Literal["simple","martial"], ranged: bool,
       damage_die: str, damage_type: DamageType, finesse: bool, two_handed: bool,
       versatile_die: str | None)                          # ranged = the table's Ranged group only
GearItem(id: str, name: str, description: str = "")        # packs: SRD contents sentence
GearRef(kind: GearKind, id: str, quantity: int = 1)        # weapon_category id: simple|simple_melee|
                                                           # martial|martial_melee
EquipmentOption(label: str, items: list[GearRef])          # label = the SRD bullet's wording
EquipmentChoice(options: list[EquipmentOption])            # min_length=1; index 0 is the default
CharacterClass(name: ClassName, hit_die: int, saving_throws: list[Ability],
               skill_choices: int, skill_options: list[SkillName],
               armour_proficiencies: list[str], weapon_proficiencies: list[str],
               equipment: list[EquipmentChoice])
PointBuy(costs: dict[int,int], budget: int, minimum: int, maximum: int)
CharacterSheet(name: str, race: RaceName, character_class: ClassName, level: Literal[1] = 1,
               alignment: AlignmentName, abilities: Abilities, max_hp: int, armour_class: int,
               speed: int, saving_throws: list[Ability], skills: list[SkillName],
               equipment: list[GearRef], appearance: str, backstory: str)
```

`service.py` (WI3), called as `from . import service`:

```
races() -> list[Race]          classes() -> list[CharacterClass]   skills() -> list[Skill]
alignments() -> list[Alignment]  armours() -> list[Armour]         weapons() -> list[Weapon]
gear() -> list[GearItem]       point_buy() -> PointBuy
race(name: RaceName) -> Race   character_class(name: ClassName) -> CharacterClass
```

No arguments, no session, no I/O. Lookups index a dict built from the literals; the `Literal`
name types make a miss unreachable for a validated sheet.

`commands.py` (WI3): `character_app = typer.Typer()`, `@character_app.command("options")`, registered
`cli.add_typer(character_app, name="character")`. Exit 0, all on stdout:

```
races: 9
  Dragonborn  speed 30  Medium  strength +2, charisma +1
classes: 12
  Barbarian  hit die d12  saves strength, constitution  skills 2 of 6
    (a) a greataxe | (b) any martial melee weapon
```

Tests (WI3): `test_options.py` (AC1 counts 9/12/18/9; AC4 readers take no argument),
`test_sheet.py` (AC2 a full sheet round-trips; AC3 an unknown race, class, alignment and skill each
raise `ValidationError`), `test_commands.py` (Outcome + AC5: exits 0, prints Barbarian's `d12`, both
saves and the greataxe line).

## Order
Parallel: WI1, WI2, WI3 — all code against I1/I2 as written; WI3 runs its tests once WI1 and WI2 land. Then gates.
