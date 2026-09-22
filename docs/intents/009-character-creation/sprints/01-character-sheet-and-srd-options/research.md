---
author: architect
owner: agent
created: 2026-09-22
---
# Research: 009-01

## Facts

**Wiring a new backend module.** A flat package under `backend/app/modules/<name>/`
holding `__init__.py`, `schemas.py`, `service.py`, `commands.py`, `README.md` — `srd/` is the model.
The Typer sub-app is declared in the module (`srd/commands.py:45`), registered in one line in
`backend/app/cli.py:44-50`; no router here, so `app/api/v1/router.py` is untouched. Tests mirror at
`backend/tests/<name>/` with `__init__.py` and drive the real `app.cli.cli` through
`typer.testing.CliRunner` (`tests/srd/test_commands.py:16-26`). The suite runs
`filterwarnings = ["error"]` (`backend/pyproject.toml:68`) and builds no DB engine
(`tests/conftest.py:1-14`); pure data needs no fixture, no sub-conftest.

**SRD anchors** in `backend/content/srd/v1/SRD_CC_v5.1.md` — copy numbers from these lines, do not search.

- *Races* (chapter `:5`). Per race, anchor `A` = its `***Ability Score Increase.***` line; `Size` = `A+6`,
  `Speed` = `A+8`. `A` = Dragonborn 45, Dwarf 141, Elf 177, Gnome 215, Half-Elf 255, Half-Orc 279,
  Halfling 305, Human 339, Tiefling 357. Ignore subrace increases (`:167,201,235,329`) — no subraces.
- *Classes* (chapter `:375`). Per class, anchor `P` = its `#### Proficiencies` line; `Hit Dice` = `P-6`,
  `Armor` = `P+2`, `Weapons` = `P+4`, `Saving Throws` = `P+8`, `Skills` = `P+10`, the Equipment heading
  = `P+12` and its either/or bullets start at `P+16`. `P` = Barbarian 553, Bard 849, Cleric 1427,
  Druid 2074, Fighter 2899, Monk 3204, Paladin 3502, Ranger 4098, Rogue 4629, Sorcerer 4940,
  Warlock 5680, Wizard 6329. Cleric alone writes `### Equipment`, not `####` (`:1439`) — same offset.
  Bard's skill line is "Choose any three" (`:859`): all 18 skills.
- *Skills*: 18 names under their ability, `:6972-7004` (no Constitution skill).
- *Alignments*: the nine, with abbreviations, `:7861-7877`.
- *Armour*: table `:20327-20484`; the Dex rules, Str rule, Stealth rule and "a shield increases your
  Armor Class by 2" at `:20488-20498`; the shield row is `:20468-20482`.
- *Weapons*: table `:20649-20939`, group headers Simple Melee `:20668`, Simple Ranged `:20741`,
  Martial Melee `:20772`, Martial Ranged `:20901`; property definitions `:20602-20624`.
- *Packs*: the seven, with contents, `:19514-19526`. Foci the class lists name: arcane focus `:18968`,
  component pouch `:19113`, druidic focus `:19123`, holy symbol `:19178`.
- Point buy is **not** in the SRD — our own rule, say so in the README: costs `{8:0, 9:1, 10:2, 11:3,
  12:4, 13:5, 14:7, 15:9}`, budget 27, scores 8–15 before racial bonuses.

**Reuse.** `Abilities` (`content/schemas.py:16`) is the six scores, `ge=1 le=30`,
already reused by `playthrough/schemas.py:8` — reuse it, do not mirror. `SeedCharacter`
(`content/schemas.py:59`) and `CharacterState` (`playthrough/schemas.py:160`) are sprint 02's
targets and stay untouched.

## Decisions (technical, taken here)

1. **`CharacterSheet` lives in `character/schemas.py`; sprint 02 imports it.** `schemas.py` is public surface in
   practice — `playthrough/schemas.py:8`, `game/agent/tools.py:42` and `auth/routes.py:12` all import
   another module's schemas; AGENTS.md's `service.py`/`models.py` is an example, not a closed list.
   Blast radius in sprint 02: one import line, nothing moves.
2. **Two data files, not one** — `options.py` (WI1) and `classes.py` (WI2) — so the two authoring work
   items never touch the same file. Still plain typed literals, still no loader (AC4 holds).
3. **No `shield` gear kind.** A shield is a row of the armour table (`:20468`), so it is
   `GearRef(kind="armour", id="shield")` with `Armour(category="shield", base_ac=2)`; sprint 02 adds 2
   when `category == "shield"`. One concept, one table.
4. **A fixed equipment line is a choice with one option**, so `equipment` is a uniform
   `list[EquipmentChoice]`: sprint 04 needs no second code path, and "just the default" is index 0.
5. Both full tables are authored (class lists say "any simple weapon"); gear covers only entries the
   class lists name, a pack being one entry whose `description` is its SRD contents.

## Work items

- WI1 `character/schemas.py` + `character/options.py`: every type below, plus the races, skills,
  alignments, armour, weapons, gear/packs and point-buy literals.
- WI2 `character/classes.py`: the twelve `CharacterClass` literals from the anchors above.
- WI3 `character/service.py`, `character/commands.py`, one line in `app/cli.py`, `character/README.md`,
  `backend/tests/character/`.

All three run in parallel against the interfaces below.

## Interfaces

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

## Open questions

None: D1, D4, D7, D8, D13, D17 and D18 settle every product-visible question.
