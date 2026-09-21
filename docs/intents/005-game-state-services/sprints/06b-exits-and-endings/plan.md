---
author: sprint
owner: agent
created: 2026-09-19
---
# Plan: Sprint 06b

`research.md` covers both halves of the split sprint 06; 06a's half is merged. Only `use_exit` is in scope here.
It has **no route**: phase 8's tool layer is its only caller, so its criteria are database tests over the service.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Using an exit: it moves the actor to the scene it leads to, or — on an ending exit — completes the adventure and, after the last one, finishes the game, leaving everybody where they stand. An exit not on the actor's own scene is refused, and the refusal is written where only the DM sees it | AC2, AC3: the move and its entry; the completion, its entry, the game finishing; positions kept; the refusal raised *and* recorded | – |
| 2 | backend-python | The module docs describe the mechanic, its recorded refusal and the end of a game | AC4b | I1–I3 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I3 |

## Interfaces
- I1 `use_exit(db, *, user_id, actor_id, exit_id) -> None`. Load the object by `actor_id` alone; missing → `GameObjectNotFoundError` (`NOT_FOUND`). Then `_require_member(run_id=obj.campaign_run_id, …)`, so a foreign actor answers identically to an unknown one; `_require_writable`; the run must be `ready|active`. Resolve the actor's scene through `content.service.load_scene(campaign_id, content_version, obj.scene_id)` for the **pinned** version and match `exit_id` among its exits. `Exit.condition` is ignored — prose the agent weighs before calling (← D8). No `turn_id` parameter; phase 8 adds one when a turn exists.
- I2 Outcomes:
  - `kind='scene'` → the actor's `scene_id` becomes `exit.to`, `adventure_run_id` unchanged; append `scene_entered {adventureRunId, sceneId}` at `player`; commit.
  - `kind='adventure_end'` → the adventure run becomes `completed` with `completed_at` in one statement; append `adventure_completed {adventureRunId}` at `player`; and when that adventure is the last in `campaign.adventures` — read from the **pinned content**, not the runs table — the campaign run becomes `finished`. No position is touched. Commit.
  - Either way a successful call also records `tool_call` with `result: "ok"` at `dm` (← D11); `enter_adventure` does not, being a route rather than a tool.
- I3 The refusal that survives (← D11): the exit check runs **before** any state change. On failure the function appends `tool_call {name:"use_exit", args:{actorId, exitId}, rollIds:[], result:"refused", outcome:{reason}}` at `dm`, **commits**, then raises `ExitNotAvailableError` (new, `EXIT_NOT_AVAILABLE`, 409). `append_event` only flushes, so without that commit the caller's rollback erases the record; nothing else is pending, so the commit writes exactly that row. An actor standing nowhere at all is the same refusal, recorded the same way — one error class, not two.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_exits_and_endings.py`, every test `@pytest.mark.database`.
- AC2 → an ordinary exit moves the actor and records the new scene; an exit that is not on that scene is refused, and the refusal is in the transcript at DM visibility while the player's read shows nothing.
- AC3 → the ending exit completes the adventure, records it, finishes the game because it is the last adventure, and leaves every position as it was.

## Order
Parallel: WI1, WI2, qa.
