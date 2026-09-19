---
author: sprint
owner: agent
created: 2026-09-19
---
# Plan: Sprint 06a

`research.md` covers both halves of the split sprint 06. Only `enter_adventure`, its route and its docs are in
scope here; `use_exit` is 06b.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Entering the next adventure: its cast and every character take their places, the transcript records that it began, and a second entry — or an entry when there is nothing left to enter — is refused | AC1, AC4: the adventure run and its event; cast and characters positioned, carried items untouched; the two refusals, each its own code | – |
| 2 | backend-python | That endpoint, in the wire's vocabulary, every refusal leaving as the envelope | AC1: 201 and the shape; authentication and CSRF; each refusal's code | WI1, I1–I4 |
| 3 | backend-python | The module docs describe entering an adventure and what it positions | AC4 | I1–I4 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I4 |

## Interfaces
- I1 `POST /api/v1/playthrough/campaign/{run_id}/adventure`, `CsrfAuth`, no body, 201 → `AdventureRunRead {id, adventureId, status, startedAt}`. Entry does **not** change the campaign run's status — the first narration does (← D3). Refusals translate as everywhere: `except PlaythroughError as exc: raise ApiError(exc.code) from exc`.
- I2 `enter_adventure(db, *, user_id, run_id) -> AdventureRun`: `_require_member` → load the run → `_require_writable` → status must be `ready|active`, else `InvalidRunStatusError` → load the pinned campaign → next is the first id in `campaign.adventures` with no `adventure_runs` row in this run; none left → `AdventureExhaustedError` (this is also AC4's re-entry refusal) → insert `AdventureRun(status='active')`, flush, the two position statements, `append_event` `adventure_started` at `player` with `{adventureRunId}`, one commit. An `IntegrityError` on `uq_adventure_runs_active` → roll back → `AdventureActiveError`.
- I3 Positioning, two `UPDATE objects` inside that transaction:
  1. the cast — `WHERE campaign_run_id=<run> AND source_adventure_id=<adv> AND owner_object_id IS NULL SET adventure_run_id=<new>, scene_id=source_scene_id`
  2. the characters — `WHERE campaign_run_id=<run> AND member_id IS NOT NULL SET adventure_run_id=<new>, scene_id=<entry_scene>`

  The second catches a character created before any adventure existed: it has no `source_adventure_id` to match on. Carried rows are excluded by the first and untouched by the second; nothing else is cleared.
- I4 New error classes, each a new `ErrorCode` with an `_ERROR_INFO` row, 409: `AdventureActiveError → ADVENTURE_ACTIVE`, `AdventureExhaustedError → ADVENTURE_EXHAUSTED`.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_adventures_entered.py`; the positioning `@pytest.mark.database`.
- AC1 → entering answers the adventure run, records that it began, and puts the cast and the character in place.
- AC1 → a second entry while one is active is refused with its own code, against a campaign authoring two adventures.
- AC4 → entering with nothing left to enter is refused with the other code.

## Order
Parallel: WI1, WI3, qa. Then: WI2.

## Note
With the shipped one-adventure campaign, a second entry always meets "nothing left to enter" first, so the
"one is already active" refusal needs a fixture campaign with two adventures to be reachable at all.
