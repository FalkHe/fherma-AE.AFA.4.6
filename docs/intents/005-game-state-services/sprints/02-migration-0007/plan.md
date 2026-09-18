---
author: sprint
owner: agent
created: 2026-09-18
---
# Plan: Sprint 02

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The database accepts the lifecycle this phase writes: the five run statuses with `setup` the default, a creature with no template, the twelve event types, a decimal temperature — one additive revision that also undoes itself; every engine-free test that still describes the old world is rewritten | AC1–AC4: the new CHECK sets and default as the revision file declares them; the old-world assertions in `test_models.py` and the two 003 acceptance tests restated, not deleted; `test_migration_0007.py` in the house recorder style | – |
| 2 | backend-python | Module README and the playthrough doc name the new status set, the optional template and the twelve event types | AC4: prose matches I1–I4 | I1–I4 |
| qa | qa | Real-database acceptance tests, one per criterion | below | I1–I4 |

## Interfaces
- I1 Revision `0007`, `down_revision = "0006"`, file `0007_<slug>.py` (`revision = "0007"`). `downgrade` restores the three prior CHECKs, the prior default and `NOT NULL` exactly.
- I2 `ck_campaign_runs_status` — `status IN ('setup','ready','active','archived','finished')`, `server_default 'setup'`.
- I3 `objects.template_id` drops `NOT NULL`; no new constraint. `ck_objects_stats_creature_only` and `ck_objects_hp_range` untouched.
- I4 `ck_events_type` — `type IN ('narration','player_action','roll_requested','roll','question','tool_call','scene_entered','adventure_started','adventure_completed','system','error','warning')`. `ck_events_visibility` untouched. `CampaignRun.temperature` is `Mapped[Decimal | None]` over the unchanged `Numeric(3, 2)`.
- I5 `op` calls pass the **bare** name (`"status"`, `"type"`); the metadata naming convention supplies the `ck_<table>_` prefix on both sides, so `downgrade` re-emits what `0003`/`0006` emitted.
- I6 Shared fixture: `playthrough_db` (`tests/playthrough/conftest.py:13`); every real-database test is `@pytest.mark.database` and wraps its own `asyncio.run(...)`. Roll the session's transaction back before running `alembic` in a subprocess, or `DROP CONSTRAINT` deadlocks.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_migration_0007.py`, `@pytest.mark.database` over `playthrough_db`.
- AC1 → a run inserted with no status reads back `setup`; all five are accepted, `paused` refused.
- AC2 → a creature with no template and a member inserts; the creature-only and hit-point rules still bite.
- AC3 → each of the twelve event types inserts; a thirteenth is refused.
- AC4 → after `alembic downgrade 0006` the three CHECKs, the default and the `NOT NULL` read back as `0006` left them.

## Order
Parallel: WI1, WI2, qa.

## Note
The schema and the tests pinning the old sets are one work item on purpose: splitting them would leave the suite red between two commits.
