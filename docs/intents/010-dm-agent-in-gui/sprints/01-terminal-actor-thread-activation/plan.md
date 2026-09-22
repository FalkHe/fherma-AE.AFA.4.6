---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 01

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A run-scoped read that returns the caller's own character in that run, with a not-found error when they have none | own character returned; foreign/unknown run rejected as run-not-found; member without a character raises the new not-found error | – |
| 2 | backend-python | The terminal game resolves the acting hero from the signed-in player and the run, and keeps the Dungeon Master's memory under the run id | run id alone starts play with the hero acting; `--actor` still overrides; thread defaults to the run id; `--thread-id` still overrides; missing character exits 1 with its message | interface I1 |
| 3 | backend-python | The first narration of a run moves it from ready to in progress; later narrations and non-ready runs are untouched | ready run activates once; already-active run unchanged; finished/archived run not activated and no error raised | – |

## Interfaces
- I1 (`app/modules/playthrough/service.py`):
  `async def get_member_character(db: AsyncSession, *, user_id: str, run_id: str) -> GameObject`
  `_require_member` first (foreign/unknown run → `CampaignRunNotFoundError`), then the single `GameObject`
  with `campaign_run_id == run_id`, `kind == "creature"`, `member_id == member.id`. No row →
  `CharacterNotFoundError(run_id)` in `playthrough/errors.py`, `code = ErrorCode.NOT_FOUND`, message naming
  the run. Read-only: no commit, no event, no status change. WI2 imports it as
  `playthrough_service.get_member_character` and needs no new error handling — `PlaythroughError` already
  exits 1 (`game/commands.py:191-193`).
- I2 (`app/modules/game/agent/nodes.py`, inside `record_narration`'s `if text:` branch, after `append_event` + commit):
  read the run via `playthrough_service.get_campaign_run`, and only when `run.status == "ready"` call
  `playthrough_service.activate_campaign_run`. WI3 owns the stub updates this forces on
  `backend/tests/game/test_service.py` (its fake db cannot answer a real query).

## Acceptance tests (qa)
No qa work item — the backlog reserves acceptance tests for sprint 03. Each work item's own tests cover
its criteria: AC1 → WI2, AC2 → WI2 (thread id), AC3 → WI3, AC4 → WI3.

## Order
Parallel: WI1, WI2, WI3. WI2 implements against I1 without waiting for WI1.
