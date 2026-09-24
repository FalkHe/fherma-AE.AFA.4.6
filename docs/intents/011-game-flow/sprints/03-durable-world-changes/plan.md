---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 03

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A successful fixture action is kept in the fixture's own state and survives a reload; fixture interaction, take, drop, give and exit use return the shared typed result (I1, I2), exit use knows its turn; the always-refusing item use, the acted-already gate and the damaged-hit scan are gone with their tests; the old tools read the typed results | fixture stays open after reload; unreachable item is a typed refusal, not an error; exit use records the turn | – (lands I1 in its first commit) |
| 2 | backend-python | Hostility change, scene departure, entering the next adventure and finishing a run for victory, defeat or authored ending exist as rules-layer functions with typed results and object-state keys (I2, I3) | hostility flag set; departed actor has no position and remembers where it left; finish_run sets the run finished with the outcome recorded | I1 type only |
| 3 | backend-python | The rules layer records player actions, answers, narration and mechanic outcomes (I2); the game module and its graph nodes contain no commit or event append of their own | each record function writes its event with the turn; game module has no commit | I1 landed |

## Interfaces
- I1 (playthrough/schemas.py, internal):
  ```python
  @dataclass(frozen=True)
  class MutationResult:
      status: Literal["ok", "refused"]
      reason: str | None = None
      event_ids: list[str] = field(default_factory=list)
      facts: dict[str, Any] = field(default_factory=dict)
  ```
- I2 (playthrough/service.py; all async, `db` first, keyword-only after):
  ```python
  interact(*, user_id, actor_id, object_id, action, roll_id=None, turn_id=None) -> MutationResult   # facts: success, dc, total, bypassedBy, outcome
  take(*, user_id, actor_id, item_id, turn_id=None) -> MutationResult
  drop(*, user_id, actor_id, item_id, turn_id=None) -> MutationResult
  give(*, user_id, from_id, to_id, item_id, turn_id=None) -> MutationResult
  use_exit(*, user_id, actor_id, exit_id, turn_id=None) -> MutationResult    # facts: kind scene|adventure_end, sceneId, runFinished
  set_hostility(*, user_id, actor_id, hostile: bool, turn_id=None) -> MutationResult
  leave_scene(*, user_id, actor_id, turn_id=None) -> MutationResult
  enter_next_adventure(*, user_id, run_id, turn_id=None) -> MutationResult
  finish_run(*, user_id, run_id, outcome: Literal["victory","defeat","authored"], turn_id=None) -> MutationResult
  record_player_action(*, user_id, run_id, text, turn_id, answers_question_id=None) -> Event
  record_answer(*, user_id, run_id, text, question_id, turn_id) -> Event
  record_narration(*, user_id, run_id, text, turn_id, usage=None) -> Event
  record_outcome(*, user_id, run_id, name, args, outcome, turn_id, roll_ids=()) -> Event
  ```
- I3 object-state keys (`GameObject.state`, reassigned whole): fixture `state["fixture_outcomes"][action] = {"success": prose, "turnId": id|null}`; creature `state["hostile"]: bool` (absent = undecided, authored disposition applies); departure `state["left_scene"] = {"sceneId", "adventureRunId"}` with `scene_id`/`adventure_run_id` cleared together.
- Refusals: expected mechanic refusals return `status="refused"` after the existing dm tool_call refusal row; not-found, archived, invalid-status, roll errors and infrastructure keep raising. Run ending: `finish_run` sets `status="finished"` and appends one player-visible `system` event with `details.outcome`; `use_exit`'s last-adventure branch calls it with `authored`.

## Acceptance tests (qa)
No qa agent (owner: reduce testing); WI tests cover AC1–AC4.

## Order
Parallel: WI1, WI2. Then: WI3 once WI1 has landed I1.
