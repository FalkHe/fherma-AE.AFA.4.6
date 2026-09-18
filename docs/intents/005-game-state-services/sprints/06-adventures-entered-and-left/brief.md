---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 06: adventures are entered and left by name

## Task
Implement adventure progress: enter the next adventure and position its cast and the characters, and `use_exit` as the one mechanic that moves an actor to another scene or — on an `adventure_end` exit — completes the adventure run and finishes the campaign run after the last one, leaving positions intact.

## Outcome
`POST …/adventure` enters the next id of `campaign.adventures[]`, positions that adventure's cast and the character in
`entry_scene` and appends `adventure_started`, a second call while one is active is refused, `use_exit` on a `scene`
exit moves the actor and appends `scene_entered`, an exit not on the actor's current scene is refused, and the
`adventure_end` exit completes the adventure run and — being the last adventure — finishes the campaign run without
clearing anybody's position.

## Acceptance criteria
- AC1: `POST /api/v1/playthrough/campaign/{id}/adventure` on a `ready|active` run with no active adventure answers 201 with the adventure run and appends `adventure_started`; the cast of that adventure and every member character are positioned (`UPDATE … SET adventure_run_id, scene_id = source_scene_id` / `entry_scene`); a second call answers a domain code mapped from `IntegrityError` on `uq_adventure_runs_active` (← research §C5).
- AC2 (`@pytest.mark.database`): `use_exit(db, *, user_id, actor_id, exit_id)` on a `scene` exit of the actor's current scene rewrites the actor's position and appends `scene_entered {adventureRunId, sceneId}`; an `exit_id` not on that scene (resolved through `content.service.load_scene` for the pinned version) is refused and recorded as a `tool_call` `refused` at `dm` visibility.
- AC3 (`@pytest.mark.database`): `use_exit` on the `adventure_end` exit sets the adventure run `completed`/`completed_at`, appends `adventure_completed`, and — the adventure being the last in `campaign.adventures[]` — sets the campaign run `finished`; every positioned object keeps its position.
- AC4: entering when every adventure is completed, or re-entering a completed one, is refused; docs updated.

## Decisions
← D1, D3, D8, D11, D12 · research §C4, §C5

## Assumptions
- "Next adventure" = first id of `campaign.adventures[]` without an `adventure_runs` row; no re-entry (003 ASSUMPTION 6).
- `use_exit` ignores `Exit.condition` — prose the agent weighs before calling the tool (← D8).
- "Last adventure" is decided against the pinned content, not the runs table.

## Out of scope
No travel between adventures · no fixture state flips on entry · no intro/outro narration (phase 8) · no journal entry (phase 6) · no roll needed to use an exit.
