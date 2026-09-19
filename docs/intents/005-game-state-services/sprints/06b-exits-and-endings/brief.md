---
author: sprint
owner: human
created: 2026-09-19
stage: approved
---
# Sprint 06b: an exit moves the party, ends the adventure, or finishes the game

Half of the approved sprint 06, split at the mechanic boundary on the precedent the product owner set for
sprint 05. The other half is 06a, which must land first. Task, outcome and criteria are that brief's,
partitioned — nothing is added.

## Task
Implement `use_exit` as the one mechanic that moves an actor to another scene or — on an `adventure_end` exit — completes the adventure run and finishes the campaign run after the last one, leaving positions intact.

## Outcome
`use_exit` on a `scene` exit moves the actor and appends `scene_entered`, an exit not on the actor's current scene is
refused and recorded, and the `adventure_end` exit completes the adventure run and — being the last adventure —
finishes the campaign run without clearing anybody's position.

## Acceptance criteria
- AC2 (`@pytest.mark.database`): `use_exit(db, *, user_id, actor_id, exit_id)` on a `scene` exit of the actor's current scene rewrites the actor's position and appends `scene_entered {adventureRunId, sceneId}`; an `exit_id` not on that scene (resolved through `content.service.load_scene` for the pinned version) is refused and recorded as a `tool_call` `refused` at `dm` visibility.
- AC3 (`@pytest.mark.database`): `use_exit` on the `adventure_end` exit sets the adventure run `completed`/`completed_at`, appends `adventure_completed`, and — the adventure being the last in `campaign.adventures[]` — sets the campaign run `finished`; every positioned object keeps its position.
- AC4b: the module docs describe the mechanic, its recorded refusal and the end of a game.

## Decisions
← D1, D8, D11, D12 · research §C4, §C5

## Assumptions
- `use_exit` ignores `Exit.condition` — prose the agent weighs before calling the tool (← D8).
- "Last adventure" is decided against the pinned content, not the runs table.
- No route: phase 8's tool layer is the only caller, so the criteria are database tests over the service.

## Out of scope
Entering an adventure — 06a · no roll needed to use an exit · no outro narration (phase 8) · no journal entry (phase 6).
