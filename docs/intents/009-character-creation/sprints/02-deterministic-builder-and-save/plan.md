---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 02

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | `character/builder.py` pure functions, `character/errors.py`, `SheetItem` / `proficiency_bonus` / `CharacterCreateRequest` additions to `character/schemas.py`, `service.build_sheet`, README update | AC1 legal spread accepted, illegal refused with a message naming what is wrong · AC2 rolled scores come from the dice seam, reproducible with a scripted rng · AC3 HP, AC, saves and a weapon's to-hit/damage derived, never taken from the caller | – |
| 2 | backend-python | Widened `CharacterState`; `create_character` accepting `CharacterSheet`, writing sheet-born carried rows with attacks in state; `_attacks_for` guard resolved in `_append_roll_requested`; optional route body; regenerated API client | AC4 a sheet-born character survives `damage` with every field intact · AC5 attack with a sheet-born weapon resolves and the seed hero's template item still works · AC6 route without body = seed hero, with body = described character, run ready · AC7 lint + committed `schema.d.ts` | I1 (codes against it; runs tests once WI1 lands) |

No qa work item (backlog: black-box tests only in sprint 05). One test per criterion.

## Interfaces
- I1: every signature and model under `research.md → Interfaces`, `character/` block — `SheetItem`, `CharacterCreateRequest`, `CharacterSheet.equipment: list[SheetItem]`, `CharacterSheet.proficiency_bonus`, the builder functions, `CharacterBuildError`, `service.build_sheet`. WI1 defines, WI2 consumes.
- I2: the `playthrough/` block of `research.md → Interfaces` — `CharacterState` additions, `create_character(sheet: CharacterSheet | SeedCharacter | None)`, `derive_formula(..., item: GameObject | None)`, `_attacks_for(..., item)`, the route body and error mapping. WI2 owns all of it; WI1 touches nothing under `playthrough/` and uses `dice._ability_modifier` and `dice.roll` read-only.
- Technical decisions 1–5 of `research.md` are binding for both.

## Order
Parallel: WI1, WI2 (WI2 waits for WI1's schema additions before running its tests). Then gates incl. `make backend-test-db`.
