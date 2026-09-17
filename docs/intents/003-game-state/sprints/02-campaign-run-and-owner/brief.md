---
author: sprint
owner: human
created: 2026-09-16
stage: draft
---
# Sprint 02: a campaign run and its owner

## Outcome
A campaign run and its owner survive a migration round trip: on a fresh database `upgrade head` accepts a campaign
run with an owner row, an untitled run and a third run of the same campaign for the same user, while refusing the
same user twice in one run and an unknown status — and `downgrade base` leaves the baseline exactly as it was.

## Acceptance criteria
*Each AC is a `@pytest.mark.database` test over `playthrough_db` (sprint 01's shared fixture): green under `make backend-test-db`, skipped under `make backend-test` (← D15).*
- AC1: the migrated scratch database carries `campaign_runs` and `campaign_run_members`, with `campaign_id`, `content_version`, `title`, `status`, the four override columns and the timestamps.
- AC2: a campaign run with `title = NULL` inserts (← D11); a second and third run of the same `campaign_id` for the same user insert (← D1); the four override columns accept NULL and nothing writes them (← D6).
- AC3: `status` accepts `active`, `archived`, `finished` and raises on anything else; a second `campaign_run_members` row for the same `(campaign_run_id, user_id)` raises on the unique constraint; deleting the `users` row removes the member row.
- AC4: `alembic downgrade base` on the scratch database leaves only `users`, `sessions` and SRD's own table — no leftover table, index or constraint of ours; `make backend-test`, `make backend-test-db` and `make lint` all pass.

## Decisions
← D1, D2, D3, D6, D7, D9, D11, D14, D15

## Assumptions
- Adds migration revision `0003` on top of SRD's `0002`; later sprints add their own and never edit it.
- Creates `backend/app/modules/playthrough/` (`models.py`, `README.md`), tests under `backend/tests/playthrough/` beside sprint 01's `conftest.py`, and the one `from app.modules.playthrough import models` line in `alembic/env.py` (← D14).
- Carries assumptions 1 (VARCHAR + CHECK, not Postgres enums), 2 (cascades declared though nothing deletes), 7 (no `archived_at` / `finished_at`) and 15 (`role` has the single value `owner`) of `decisions/model.md`.

## Out of scope
No service, route, HTTP surface, CLI or phase-5 lifecycle · the shared fixture itself (01) · the other tables (03–05) · doc corrections (06).
