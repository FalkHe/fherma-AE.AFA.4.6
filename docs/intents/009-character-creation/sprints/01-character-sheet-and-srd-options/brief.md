---
author: fhit:architect
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 01: character sheet and SRD options

## Task
Open a `character` module holding the sheet a created character is described by and the SRD facts a
player may choose from, hand-authored as data from `backend/content/srd/v1/SRD_CC_v5.1.md`: nine races
(ability bonuses, speed), twelve classes (hit die, saving throws, skill list, either/or starting
equipment), the eighteen skills with their ability, the nine alignments, the point-buy cost table and the
armour values the class equipment lists use. Expose reading functions over that data and a module README.

## Outcome
A short terminal command prints the nine races and twelve classes with hit die, saving throws and
equipment choices, and the printed numbers match the SRD text.

## Acceptance criteria
- AC1: All nine races and all twelve classes are offered, each with the numbers a sheet derives from
  (← D1, D4).
- AC2: The sheet shape covers name, race, class, level 1, alignment, six ability scores, hit points,
  armour class, speed, saving throws, skills, equipment, looks and backstory (← D9, D14).
- AC3: A sheet with a race, class, alignment or skill outside the SRD lists is refused by validation
  (← D1, D7, D13).
- AC4: The data is read from the module itself — no database, no file loader, no SRD search at runtime.
- AC5: Tests live under `backend/tests/character/`, assert the counts and one class's numbers against the
  SRD, and pass with warnings-as-errors.

## Decisions
← D1, D4, D7, D8, D13, D18

## Assumptions
- Data is authored as typed Python literals in the module, not JSON — one file, no loader.
- Level 1 only; no proficiency-bonus progression, no subclasses, no spell lists.
- Skills a class itself grants are recorded per class in SRD order for the auto-fill of sprint 04 (← D18).
- Alignment is stored as one of the nine names, as plain text.

## Out of scope
No agent, no derivation maths, no saving, no HTTP route, no CLI beyond the one read command.
