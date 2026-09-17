---
author: sprint
owner: agent
created: 2026-09-17
---
# Plan: Sprint 02 — a campaign run and its owner

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A new module owning the two game-state entities as declared tables, plus its module doc and the one line that makes the schema tooling aware of it. | Every column's type, length, nullability and default · the status and role value sets · the uniqueness of one member per run · both cascades | I1 |
| 2 | backend-python | The schema step that creates those two tables on an existing database and removes them again, chained after the rules-corpus step. | It declares the right position in the chain · it creates exactly the columns, constraints and index of I1 · undoing reverses it exactly | I1 |
| 3 | backend-python | Acceptance tests proving the four criteria against a real, migrated database. | See below | I1, and green only once WI1+WI2 land |

## Interfaces
- **I1 — the two tables, binding on WI1, WI2 and WI3 alike.** Take the column tables, constraint names, defaults, cascades, the index, the revision id `0003` / `down_revision = "0002"` and the `upgrade`/`downgrade` call order **verbatim** from `research.md → Interfaces`; it is the single source and neither implementer may deviate. Two traps repeated here because both sides hit them independently: a check constraint takes the **short** name (`name="status"`, never the full `ck_…`), in the migration as well as the model; and `updated_at` carries `onupdate` in the model only, never in the migration.

## Acceptance tests (qa → WI3)
- AC1 → both tables and every named column are present after the migration runs.
- AC2 → an untitled run inserts; a second and third run of the same campaign for the same user insert; the four override columns take no value and stay empty.
- AC3 → each of the three statuses inserts, a fourth value is refused; the same user twice in one run is refused; removing the user account removes the membership.
- AC4 → undoing this step alone leaves the database exactly as it was before it, and undoing everything still runs clean. *The criterion as written asks that undoing everything leave the accounts and rules tables standing, which cannot hold — they belong to earlier steps. This is the workable reading; recorded under Issues.*

## Order
Parallel: WI1, WI2, WI3 — all three bind to I1, which is fixed. Gates last.
