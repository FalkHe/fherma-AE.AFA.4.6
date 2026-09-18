---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
stage: done
---
# Progress: Sprint 01

| WI | Status | Note |
|---|---|---|
| 1 | done | schema, loader rules R9-R11/R14 restated, R19/R20 added, fixture repaired |
| 2 | done | greenhollow ending exit, exit ids, four item templates, id pack; shipped-tree coverage restored over rounds 2-3 |
| 3 | done | authoring guide and module README |
| qa | done | 4 acceptance tests, red before implementation |

Status: `open | running | done | failed`

## Issues

- `AGENTS.md → Workflow` names the agent account `st3lla`; `glab` is signed in as `st3ll4` (display name Stella). Same
  account, leetspeak spelling; treated as a typo and the run continued.
- Research raised a product-visible question — the shepherd's knife is authored as Mira's evidence and the seed
  character is described carrying a spear, so the brief's assumption puts one object in two places. The brief is
  human-approved and states the assumption explicitly, so it stands; recorded as a backlog proposal instead of a veto.

## Backlog proposals

- The seed character's starting pack contains Mira's shepherd's knife, which the adventure prose keeps behind the bar
  as evidence while describing the character carrying a spear — author a spear item and leave the knife with Mira.
- A scene with no exits that is not the ending is now a dead end and no rule refuses it.

## Verify

Round 1: changes-requested — `backend/tests/content/test_shipped_tree.py` was rewritten wholesale, dropping five
shipped-content regression tests this sprint did not invalidate (placements, `bypassed_by` cardinalities,
`definitions/` layout, no-old-keys); AC1-AC4 all OK.

Round 2: changes-requested — the seven named tests are restored unweakened, but
`test_loaded_campaign_exercises_every_pinned_mechanism_c27a`'s `carries` and item-`attacks` assertions were
not; no test in `backend/tests/` pins the shipped placements' carried items. AC1-AC4 OK both rounds.
Round cap reached: the verdict stood, MR !24 went to draft and backlog row 01 was marked `failed`.

Round 3: approve — reopened at the product owner's request after sprint 02 merged. `main` merged into the branch
(only conflict: `backlog.md`'s status column), `test_loaded_campaign_exercises_every_pinned_mechanism_c27a`
restored byte-identical to `main`, verified to fail when the goblin chief's `carries` is emptied. Gates green:
lint, 703 backend, 53 frontend, 36 database. MR !24 taken out of draft and approved; backlog row 01 `done`.
