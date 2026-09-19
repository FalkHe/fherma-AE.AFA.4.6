---
author: sprint
owner: human
created: 2026-09-19
stage: approved
---
# Sprint 06a: an adventure is entered and its world takes its places

Half of the approved sprint 06, split at the mechanic boundary on the precedent the product owner set for
sprint 05: two mechanics, a route, four error classes and two positioning statements were one sprint too many.
The other half is 06b. Task, outcome and criteria are that brief's, partitioned — nothing is added.

## Task
Implement adventure progress' first half: enter the next adventure and position its cast and the characters.

## Outcome
`POST …/adventure` enters the next id of `campaign.adventures[]`, positions that adventure's cast and the character
in `entry_scene` and appends `adventure_started`; a second call while one is active is refused, and so is entering
when every adventure is completed.

## Acceptance criteria
- AC1: `POST /api/v1/playthrough/campaign/{id}/adventure` on a `ready|active` run with no active adventure answers 201 with the adventure run and appends `adventure_started`; the cast of that adventure and every member character are positioned (`UPDATE … SET adventure_run_id, scene_id = source_scene_id` / `entry_scene`); a second call while one is active answers a domain code mapped from `IntegrityError` on `uq_adventure_runs_active` (← research §C5).
- AC4: entering when every adventure is completed, or re-entering a completed one, is refused; docs updated.

## Decisions
← D1, D3, D12 · research §C4, §C5

## Assumptions
- "Next adventure" = first id of `campaign.adventures[]` without an `adventure_runs` row; no re-entry (003 ASSUMPTION 6).
- Entry does not change the campaign run's status — the first narration does (← D3).

## Out of scope
`use_exit` and everything it does — 06b · no travel between adventures · no fixture state flips on entry · no intro narration (phase 8) · no journal entry (phase 6).
