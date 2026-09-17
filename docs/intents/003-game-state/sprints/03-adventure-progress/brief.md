---
author: sprint
owner: human
created: 2026-09-16
stage: approved
---
# Sprint 03: adventure progress that cannot contradict itself

## Outcome
Adventure progress cannot contradict itself: a campaign run records one row per adventure entered, refuses the same
adventure twice, refuses a second *active* adventure beside the first, and refuses a row marked completed with no
completion time.

## Acceptance criteria
*Each AC is a `@pytest.mark.database` test over `playthrough_db` (sprint 01's shared fixture): green under `make backend-test-db`, skipped under `make backend-test` (← D15).*
- AC1: the migrated scratch database carries `adventure_runs` with `campaign_run_id`, `adventure_id`, `status`, `started_at`, `completed_at`, `updated_at` — and **no scene column**: position belongs to the creature (← D12).
- AC2: inserting two rows with the same `(campaign_run_id, adventure_id)` raises on the unique constraint (one row per adventure entered, ← D10).
- AC3: with one `status = 'active'` row present, a second `active` row in the same campaign run raises on the partial unique index, while an `active` row in a *different* campaign run inserts.
- AC4: `status` accepts only `active` and `completed`; `completed` without `completed_at`, and `completed_at` on an `active` row, both raise on the check; deleting the parent `campaign_runs` row removes its adventure runs.
- AC5: `alembic downgrade -1` drops this table and leaves sprint 02's two intact; `make backend-test`, `make backend-test-db` and `make lint` all pass.

## Decisions
← D8, D9, D10, D12, D14, D15

## Assumptions
- Adds migration revision `0004` on top of sprint 02's `0003` and does not edit it.
- Carries assumptions 4 (what "this adventure is done" means — the *rule* that writes it is phase 5's), 5 (the `active | completed` value set, no `abandoned`/`failed`) and 6 (an adventure is entered at most once) of `decisions/model.md`. The active adventure is derived from `status`, never from a pointer on the campaign run.

## Out of scope
No service, route, HTTP surface or phase-5 lifecycle — nothing enters, advances or completes an adventure here · no encounter, initiative or turn order (← D8) · objects and their position (04).
