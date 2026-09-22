---
author: architect
owner: agent
created: 2026-09-22
---
# Research: 009-02

## Facts

**Today.** `create_character` (`playthrough/service.py:456`) already takes `sheet: SeedCharacter |
None`, writes the creature row with `CharacterState(...).model_dump()` (`:503`), one carried row per
`sheet.inventory` entry via `_build_object` from `loaded.object_templates[template_id]` (`:518-527`), sets
`run.status = "ready"` and commits once. The route (`routes.py:93`) passes no `sheet`; `CharacterRead`
(`schemas.py:149`) stays as it is. `CharacterState` (`schemas.py:160`) carries only abilities, race,
character_class, background, appearance, down — a plain `BaseModel`, so `damage`'s re-validate-and-write-back
(`service.py:2276`) silently drops anything else: that is AC4's bug today.

**Dice.** `_rng()` (`dice.py:68`), `roll("NdM±K")` (`:76`, 20 dice / 100 faces cap), `_ability_modifier`
(`:98`), `derive_formula` (`:155`). `derive_formula` has one caller, `_append_roll_requested`
(`service.py:782`), which holds `db` and `run`. `_attacks_for` (`:136`) reads `context["item_id"]` as a
**content template id** (`load_object_template`, `:143`; tests pass `"shepherds-knife"`,
`tests/playthrough/test_service_attack_and_damage.py:222`), while `attack`'s own `item_id` is an object row
id (`service.py:2019`) — two id spaces under one name. A character with no `item_id` raises (`:148`).

**A template-less row is safe everywhere else.** `objects.template_id` is nullable, no check constraint
(`models.py:167`) → no migration. Outside `content`, only `dice.py:116,143,149`, `service.py:1507` (already
guarded, `:1494`) and `game/agent/tools.py:232` (an LLM-supplied template id, unrelated) load templates;
`take`/`drop`/`give`/`use_item` touch rows only, and the DM's context lists carried items by
`GameObject.name` (`game/agent/nodes.py:131-141`). Only `_attacks_for` needs a guard.

**Imports.** `character/` imports nothing from playthrough; `dice.py` imports only `playthrough.models`,
`playthrough.schemas` and `content` (`:36-40`); both `__init__.py` are empty. So `character.builder →
playthrough.dice` plus `playthrough.{service,routes} → character.{schemas,service}` is acyclic — no lazy
imports. `CharacterSheet` therefore stays in `character/schemas.py` (sprint 01), against the brief's
assumption: moving it would drag `Race`/`GearRef` along for no gain.

**Data on hand.** `Abilities` (`content/schemas.py:16`); `Attack(name, to_hit, damage)` (`:25`) is
alias-free and round-trips through JSONB unchanged; `POINT_BUY` (`options.py:725`); `Armour.dex_bonus`
`full|max2|none` already encodes the AC rule (`character/schemas.py:114`); `damage_die` is a rollable
`"1d8"` (`options.py:472`). Option index 0 of Fighter, Paladin and Wizard holds a `weapon_category` ref
(`classes.py:342,445,762`), so defaults need a substitution.

**API.** fastapi 0.141.1 (`backend/uv.lock:262` — context7): a body parameter defaulting to `None` makes
the body optional. `ApiError(code, details=…)` (`core/errors.py:99`); `make generate-api` needs `make up`
(`Makefile:86`).

**Test models.** `tests/playthrough/test_service_attack_and_damage.py` — `@pytest.mark.database`, the
`playthrough_db` scratch fixture (`conftest.py:12`), `_ScriptedRandom` over `dice._rng`, one `asyncio.run`
per scenario; `test_routes.py` for the route; `tests/character/test_sheet.py` for pure functions.

## Decisions (technical, taken here)

1. `CharacterSheet.equipment` becomes `list[SheetItem]` (resolved: name + derived attacks) instead of
   `list[GearRef]`: one list, and `create_character` writes rows verbatim without calling back into
   `character`. Costs one line in `tests/character/test_sheet.py:29`.
2. A `weapon_category` ref resolves through a fixed table — `simple`/`simple_melee` → `mace`,
   `martial`/`martial_melee` → `longsword` — so every default is a real item. Sprint 04 may add a named
   pick later.
3. Starting gear is proficient by definition (`proficient=True`); the prose proficiency lists are never
   parsed.
4. `CharacterState.background` keeps its name and takes `sheet.backstory`; every new field carries a
   default, so the seed path is untouched.
5. Sheet-born rows carry `state = {"srd_id": …, "attacks": [...]}`; armour counts into `armour_class` at
   build time and is never re-read from a row.

## Work items

- **WI1 `character/`**: `builder.py`, `errors.py`, the `SheetItem`/`proficiency_bonus` additions to
  `schemas.py`, `service.build_sheet`, tests AC1–AC3.
- **WI2 `playthrough/`**: widened `CharacterState`, `create_character(sheet=…)`, the `_attacks_for` guard
  and its resolution in `_append_roll_requested`, the optional route body, `make generate-api`, tests
  AC4–AC6. AC7 is both lint suites plus the committed `schema.d.ts`.

## Interfaces

`character/schemas.py` (WI1), additions only:

```
class SheetItem(GearRef):        # kind, id, quantity inherited
    name: str
    attacks: list[Attack] = []   # weapons only; content.schemas.Attack
CharacterSheet.equipment: list[SheetItem]
CharacterSheet.proficiency_bonus: int = 2

class CharacterCreateRequest(CamelModel):
    name: str; race: RaceName; character_class: ClassName; alignment: AlignmentName
    abilities: Abilities                       # base scores, 8..15, before racial bonuses
    free_ability_bonuses: list[Ability] = []   # Half-Elf; empty = the two highest others
    skills: list[SkillName] = []
    equipment_picks: list[int] = []            # one option index per class choice; short/empty = 0
    appearance: str = ""; backstory: str = ""
```

`character/builder.py` (WI1), pure, no session:

```
point_buy_cost(scores: Abilities) -> int
validate_point_buy(scores: Abilities) -> list[str]     # [] = legal; else "constitution 17 is above 15",
                                                       # "spread costs 29 of 27 points"
suggested_scores(class_name: ClassName) -> Abilities    # [15,14,13,12,10,8] over an authored per-class
                                                        # ability order; always 27 points
roll_scores() -> Abilities        # 6 x dice.roll("4d6"), drop the lowest face; no rng parameter (← D5)
apply_race(scores: Abilities, race: Race, free: list[Ability]) -> Abilities
modifier(score: int) -> int       # dice.ability_modifier, renamed public in dice.py, not re-implemented
derive_hp(cls: CharacterClass, con_mod: int) -> int            # hit die + con mod, floor 1
derive_ac(dex_mod: int, armour: Armour | None, shield: bool) -> int
derive_saves(cls: CharacterClass) -> list[Ability]
weapon_attack(w: Weapon, scores: Abilities, proficient: bool) -> Attack   # to_hit = 2 + mod (finesse or
                                       # ranged: better of str/dex); damage = f"{w.damage_die}{mod:+d}"
resolve_equipment(cls: CharacterClass, picks: list[int]) -> list[SheetItem]
build_sheet(request: CharacterCreateRequest) -> CharacterSheet   # the one entry; raises
                                       # CharacterBuildError(messages) on an illegal spread or an
                                       # unknown pick index
```

`character/errors.py`: `CharacterBuildError(Exception)` with `code = ErrorCode.VALIDATION_ERROR` and
`.messages: list[str]`. `character/service.py` adds a delegating `build_sheet(request) -> CharacterSheet`.

`playthrough/` (WI2):

```
CharacterState += level: int = 1, alignment: str | None = None, speed: int = 30,
                 proficiency_bonus: int = 2, saving_throws: list[str] = [],
                 skills: list[str] = [], equipment: list[SheetItem] = []
create_character(..., sheet: CharacterSheet | SeedCharacter | None = None)
   # CharacterSheet -> rows with template_id=None, name=item.name,
   #   state={"srd_id": item.id, "attacks": [a.model_dump() for a in item.attacks]},
   #   one row per unit of quantity, instance_key f"{instance_key}/{item.id}:{n}"
dice.derive_formula(..., item: GameObject | None = None)
dice._attacks_for(..., item: GameObject | None = None)
   # item is not None -> [Attack.model_validate(a) for a in item.state.get("attacks", [])]
_append_roll_requested: for kind attack|damage, db.get(GameObject, context["item_id"]);
   pass it as item only when the row is in this run and template_id is None, else today's path
POST /playthrough/campaign/{runId}/character  body: CharacterCreateRequest | None = None
   # None -> today's seed hero; else character_service.build_sheet(payload) -> create_character(sheet=…)
   # CharacterBuildError -> ApiError(VALIDATION_ERROR, details={"messages": [...]}); 201 CharacterRead
```

Tests, one per criterion: AC1–AC3 in `tests/character/test_builder.py` (AC2 monkeypatches `dice._rng`);
AC4 a sheet-born character damaged, its state re-read field by field; AC5 one scenario attacking with a
sheet-born weapon and with the seed hero's `shepherds-knife`; AC6 the route with and without a body.

## Open questions

None: D1, D5, D9, D11 and D17 cover every product-visible choice.
