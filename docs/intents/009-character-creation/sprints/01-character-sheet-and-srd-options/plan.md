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
- I1: the `schemas.py` types and `service.py` signatures exactly as written in `research.md → Interfaces` (this sprint's only contract; WI1 defines, WI2 and WI3 consume).
- I2: the literals `CLASSES: list[CharacterClass]` in `classes.py` and `RACES, SKILLS, ALIGNMENTS, ARMOURS, WEAPONS, GEAR, POINT_BUY` in `options.py`, typed with the I1 models; `service.py` reads only these names.
- I3: `commands.py` exposes `character_app = typer.Typer()` with an `options` command; `app/cli.py` adds it as `character`; output shape as in `research.md → Interfaces`.

## Order
Parallel: WI1, WI2, WI3 — all code against I1/I2 as written; WI3 runs its tests once WI1 and WI2 land. Then gates.
