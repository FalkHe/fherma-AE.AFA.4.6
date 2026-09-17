---
author: sprint
owner: agent
created: 2026-09-17
---
# Plan: Sprint 03 — adventure progress that cannot contradict itself

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The adventure-progress entity added to the existing game-state module as a declared table, with its module doc updated. | Every column's type, nullability and default · the two-value status set · one row per adventure entered · at most one adventure in progress per run · a finished row must carry its finishing time and an unfinished one must not · the cascade | I1 |
| 2 | backend-python | The schema step that creates that table and its partial index on an existing database, and removes both again, chained after the previous step. | Its position in the chain · exactly the columns, constraints and index of I1 · undoing reverses it exactly | I1 |
| 3 | qa | Acceptance tests proving the five criteria against a real, migrated database. | See below | I1, green once WI1+WI2 land |

## Interfaces
- **I1 — the table, binding on all three.** Take the column table, every constraint and index with its final rendered name, the revision id `0004` / `down_revision = "0003"` and the `upgrade`/`downgrade` call order **verbatim** from `research.md → Interfaces`. Three points repeated because both implementers meet them independently: a check constraint takes the **short** name (`name="status"`, `name="completed_at"`), never the rendered one; the "at most one in progress" rule is a **partial unique index** (`postgresql_where`), so it lives in the index catalogue and never among the table constraints; and `updated_at` carries `onupdate` in the model only.

## Acceptance tests (qa → WI3)
- AC1 → the table and its six named columns are present after the migration, and there is no scene column.
- AC2 → entering the same adventure twice in one campaign run is refused.
- AC3 → a second adventure in progress beside the first is refused, while one in progress in a *different* campaign run is accepted.
- AC4 → each of the two statuses inserts and a third value is refused; finished-without-a-finishing-time and unfinished-with-one are both refused; removing the campaign run removes its adventure rows.
- AC5 → undoing one step drops this table and leaves the previous sprint's two standing.

## Order
Parallel: WI1, WI2, WI3 — all three bind to I1, which is fixed. Gates last.
