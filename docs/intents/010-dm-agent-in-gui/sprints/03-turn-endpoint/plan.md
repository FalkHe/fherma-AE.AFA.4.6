---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 03

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The turn engine: one call that runs a turn for a run and decides for itself which of the five kinds it is from what the run is actually waiting for | each kind chosen from the run's real state and never the caller's claim; an answered question stops being awaited; a roll is produced by the server and a sent number ignored; a retry resumes the saved step without repeating the roll; an opening turn writes no player row; resumed legs keep the open turn's id | – |
| 2 | backend-python | The network call itself: request and response shapes, error mapping, the module README and the regenerated typed client | every error case answers the one envelope with its stable code; the body carries nothing but optional words; the response names the turn and what is awaited next | interfaces I1, I2 |
| 3 | qa | Black-box acceptance tests for AC1–AC6, and AC7's measurement of the public host's read timeout | one test per criterion, driven only through the network call | interface I1 |

## Interfaces
- I1 — `POST /api/v1/game/runs/{runId}/turn`, `CsrfAuth`. Body: `{"text": string | null}` (≤2000 chars) and
  nothing else — the caller can name no kind and no number. 200:
  `{"turnId": string, "kind": "action"|"answer"|"roll"|"retry"|"opening", "awaiting": "none"|"roll:<id>"|"answer:<id>"}`
  (`awaiting` from `get_awaiting` after the turn). Errors: 401 `NOT_AUTHENTICATED`/`SESSION_EXPIRED`,
  403 `CSRF_TOKEN_INVALID`, 404 `NOT_FOUND` (not seated, unknown run, no character — AC6),
  409 `INVALID_RUN_STATUS` / `RUN_ARCHIVED`, 409 `ACTION_NOT_AVAILABLE` with `details:{awaiting, options}`
  (AC2: words that are not one of the offered options while an answer is awaited), 422 `VALIDATION_ERROR`,
  502 `LLM_*` (a broken turn, AC4's precondition), 500 `INTERNAL_ERROR`.
- I2 — `game.service.run_turn(db, *, user_id, run_id, text) -> TurnOutcome(turn_id, kind, awaiting)`,
  raising `PlaythroughError`/`GameError` (both carry `.code`, `.details`). Kind comes from the thread
  snapshot and the transcript, never the body, in this order: pending `question` interrupt → `answer`
  (text must equal one of the interrupt's `options`, or any text when `options` is empty; else refuse) —
  writes `player_action {text, answersQuestionId}` under the open turn, commits, then `resume(text)`;
  pending `roll_request` interrupt → `roll`, `resume({"action":"roll"})`, body text discarded (AC3);
  `next` non-empty without interrupt → `retry`, `invoke(None)` (AC4); text present → `action`, new
  `turn_id`; no text → `opening`, DM-led, no player row (AC5). Resumed kinds reuse the open turn's id.
- I3 — supporting signatures. `playthrough.service.open_turn_id(db, *, user_id, run_id) -> str | None`
  (`_require_member` first; the newest event's `turn_id`). `game.service.thread_state(agent, *, thread_id)
  -> ThreadState(interrupt: dict | None, pending: bool)`; `game.service.retry(agent, *, thread_id, context)
  -> TurnResult`; `DmContext.record_action: bool = True` (`agent/state.py:37`), honoured at `nodes.py:235`.

## Acceptance tests (qa)
AC1–AC6 → WI3, black-box through the network call only (`TestClient`, monkeypatched `game.service.run_turn`
or pinned playthrough functions per `tests/conftest.py:1-80`). AC7 → WI3 as a measurement: the number goes
into `review.md`, flagged when under 120 s.

## Order
Parallel: WI1, WI2, WI3. WI2 and WI3 are written against I1/I2 without waiting for WI1.
