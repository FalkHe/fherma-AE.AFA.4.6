---
author: fhit:architect
owner: agent
created: 2026-09-18
---
# Research: sprint 01 — the content speaks the mechanics' language

## Facts

**Shapes today.** `Exit` = `to: ContentId` (required), `description: ProseText`, `condition: ProseText | None = None`
— no `id`, no `kind` (`content/schemas.py:90`-`94`). `SeedCharacter.inventory: list[ProseText] = []`
(`schemas.py:125`), documented as "free text — not `ItemTemplate` references" (`docs/modules/content.md:310`).
`ContentModel` is `extra="forbid", frozen=True` (`schemas.py:6`-`7`); the only union precedent is the `kind`
discriminator on `ObjectTemplate` (`schemas.py:67`-`70`). No `model_validator` exists anywhere in `backend/app`.

**Rules.** R1–R18 are in use and documented (`docs/modules/content.md:360`-`377`, README `:14`) — **R19 and R20 are
free**. R9 (`service.py:191`-`196`) rejects `exit.to` that is the scene's own id or outside the adventure; R10
(`:198`-`207`) is literally `scene.exits == []` — confirmed; R11 reachability walks `exit_.to` (`:209`-`227`); R14
(`:230`, `:299`-`305`) reports a template referenced by no placement, carry or `bypassed_by`. Every rule appends
`"<path>: [Rn] <detail>"` to one `errors` list, sorted, raised as `ContentInvalidError` (`:307`-`308`,
`errors.py:11`-`19`). Schema and read failures are tagged `[READ]` / `[SCHEMA]` from the first pydantic error, loc
joined with dots (`service.py:26`-`48`). `app content validate` walks every campaign/version, prints each entry to
stderr and exits 1 (`commands.py:28`-`69`).

**Shipped tree** (real path `backend/content/campaigns/greenhollow/v1/`, not the brief's abbreviation):
`campaign.json` carries `seed_character` and all nine `object_templates`; `adventures/goblins-of-greenhollow.json`
carries the four scenes and their exits. `lair-hollow` has `exits: []`; the other three have one exit each.
Seed inventory is prose: `a spear · a wooden shield · a hooded lantern · a coil of twine · three days' rations`.
Existing item templates: `shepherds-knife` (has an attack, `1d4+2`), `bent-horseshoe`, `notched-cleaver`,
`stolen-fleece` — **none of the four new ones exists**: `wooden-shield`, `hooded-lantern`, `coil-of-twine`,
`rations` must be authored, and each is referenced only by the seed inventory, so R14 must count that reference.

**Tests that break on contact:** `tests/content/conftest.py:50`-`62` (prose inventory) and `:149`-`169`
(`mill-floor`, no exits) — the fixture campaign itself becomes invalid; `test_schemas.py:227`; `test_shipped_tree.py`
`:54`-`69` (nine templates, pinned order), `:210`, `:226`. Nothing outside `content` reads `Exit` or `seed_character`
— blast radius is the module, its tests, the shipped tree and two docs.

pydantic 2.13.5 (`backend/uv.lock:754`) — `@model_validator(mode="after")` returning `self` and raising `ValueError`
is the supported conditional-requirement hook; it yields one `value_error` at the model's own loc (context7
`/pydantic/pydantic`). Works on a frozen model: it mutates nothing. Suite runs `filterwarnings = ["error"]`.

## Work items

- **WI1 schema + loader** (AC1, AC2, AC3): `Exit` gains id and kind with the `to` invariant, `SeedCharacter.inventory`
  becomes template ids, R9/R10/R11/R14 are restated for ending exits, R19 and R20 are added — with their unit tests
  and the shared fixture campaign updated so it is valid content again. Owns `schemas.py`, `service.py`,
  `tests/content/conftest.py`, `test_schemas.py`, `test_service.py`.
- **WI2 shipped content** (AC4): `greenhollow/v1` gains the ending exit, exit ids, the four item templates and an
  inventory of template ids; the shipped-tree expectations follow. Owns `backend/content/**`, `test_shipped_tree.py`.
  Verifiable only once WI1 has landed.
- **WI3 authoring guide** (AC4): the rule table, the `Exit`/`Scene`/`SeedCharacter` sections, the constraint list, the
  worked example and the checklist describe ending exits, exit ids and the item-id inventory. Owns
  `docs/modules/content.md`, `backend/app/modules/content/README.md`.

## Interfaces

**Exit**: `id: ContentId` (required) · `kind: Literal["scene","adventure_end"] = "scene"` · `to: ContentId | None =
None` · `description: ProseText` · `condition: ProseText | None = None`. Invariant: `scene` ⇒ `to` set,
`adventure_end` ⇒ `to` absent; a violation is `[SCHEMA]`, not a rule tag. `id` is unique **per scene** only.
**SeedCharacter**: `inventory: list[ContentId] = []`.

**Rules and tags** (message text is the contract the doc and the tests share):
- R9 — applies to `kind == "scene"` exits only; message unchanged.
- R10 — `adventures/<aid>.json: [R10] no scene reachable from entry_scene carries an adventure_end exit`; reachability
  is computed before R10.
- R11 — exits with `to is None` are skipped by the walk.
- R14 — the reference set additionally holds every `seed_character.inventory` id.
- R19 — `adventures/<aid>.json: [R19] scene '<sid>': duplicate exit id '<eid>'`.
- R20 — `campaign.json: [R20] seed character inventory entry <i> names unknown object template '<id>'` and
  `campaign.json: [R20] seed character inventory entry <i> '<id>' is not an item`.

**Content keys** (pin these ids; WI2 and WI3 both quote them): exit ids `to-thornway`, `to-lair-maw`,
`to-lair-hollow`, and on `lair-hollow` `{"id": "leave-the-hollow", "kind": "adventure_end", "condition": null}`.
New `item` templates appended after `stolen-fleece`: `wooden-shield` "Wooden Shield", `hooded-lantern` "Hooded
Lantern", `coil-of-twine` "Coil of Twine", `rations` "Trail Rations", each `attacks: []` — thirteen templates in the
pinned order. Seed inventory: `["shepherds-knife","wooden-shield","hooded-lantern","coil-of-twine","rations"]`.
**Fixture campaign** (WI1): `mill-floor` gains `{"id":"out-of-the-mill","kind":"adventure_end", …}`, seed inventory
becomes `["rusty-key"]`.

## Open questions

- **Product-visible** — the shepherd's knife is authored as Mira's evidence, kept behind the bar, and the seed
  character is described carrying a spear; putting the knife in her starting pack contradicts both and makes the
  object exist twice. Alternative: author a fifth item, the spear, as her weapon and leave the knife with Mira.
  Default until vetoed: the brief's assumption.
- **Agent-level, called** — R20 carries both inventory failures rather than reusing R12/R17, so one new site adds one
  new number · a scene with `exits: []` that is not the ending is now a dead end and no rule refuses it; no per-scene
  rule this sprint, note it as a backlog proposal · the guide's worked example ships a no-exit terminal scene and
  would become invalid, so WI3 corrects it although AC4 names only the table and the scene section · the ending exit
  is unconditional, so the adventure can always be completed.
