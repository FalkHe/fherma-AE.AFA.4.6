---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: approved
---
# Sprint 02: Fights with one roll per side, real criticals and a fallen hero

## Task
Replace the current initiative handling with one hero-side roll and one automatic hostile-side roll, settled once per fight into a stable side and creature order that the hero side wins on a tie. Make attack resolution report hit, miss or critical together with the identity of the hit it produced, double only the damage dice on a critical, and make hit points, alive and downed state agree across every read and write.

## Outcome
A critical hit applies doubled dice with the flat bonus counted once, and a downed hero never appears as an available actor in any read.

## Acceptance criteria
- AC1: Given combat starts, when initiative is established, then exactly two rolls are made and the order stays fixed for the fight.
- AC2: Given equal initiative totals, then the hero side acts first.
- AC3: Given a natural 20, when damage is applied, then the dice are doubled and the flat modifier is added once.
- AC4: Given a hero at zero hit points, then every read reports them downed and ineligible to act, and the terminal game still runs a fight.

## Decisions
← intent §1.3, §1.4, §1.5; AC "every roll and mutation uses a deterministic playthrough service"

## Assumptions
- Side membership is derived from party membership and hostility; no role field is added.
- Attack keeps its existing refusal reasons.
- Tests for the old initiative and attack flow are trimmed to the intent's minimal list, not ported.

## Out of scope
The fight order kept across turns (sprint 05), monster scheduling (sprint 07).
