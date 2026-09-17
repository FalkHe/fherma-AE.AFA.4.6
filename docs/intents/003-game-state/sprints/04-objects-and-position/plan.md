---
author: sprint
owner: agent
created: 2026-09-17
---
# Plan: Sprint 04 — objects that hold only what the content declares

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The world-object entity added to the existing game-state module as a declared table, with its module doc updated. | Every column's type, nullability and default · the three-value kind set · the four fighting stats on a creature and on nothing else · health within its maximum · a position whole or absent · a carried thing with no position · one thing per key per campaign run · no limit on how many things a member holds | I1 |
| 2 | backend-python | The schema step that creates that table and its four indexes on an existing database and removes them again, chained after the previous step. | Its position in the chain · exactly the columns, constraints and indexes of I1, including that provenance columns are distinct from position columns · undoing reverses it exactly | I1 |
| 3 | qa | Acceptance tests proving the criteria against a real, migrated database. | See below | I1, green once WI1+WI2 land |

## Interfaces
- **I1 — the table, binding on all three.** Take the column table, every constraint and index with its final rendered name, every check as SQL text, the revision id `0005` / `down_revision = "0004"` and the `upgrade`/`downgrade` call order **verbatim** from `research.md → Interfaces`. Carried over: a check takes the **short** name; `updated_at` carries `onupdate` in the model only. New here: **no check may ever evaluate to unknown** — an unknown check counts as satisfied, so the rule silently never fires; a plain range check on health passes a row whose maximum is absent. Position and carried are **two separate checks**, so a failure names which fired.

## Acceptance tests (qa → WI3)
- AC1 → the three kinds are accepted and a fourth refused; a creature carries all four fighting stats, and anything else carrying any one of them is refused.
- AC3 → health below zero or above its maximum is refused; at zero, both alive and not-alive are accepted — stable is not dead.
- AC4 → a carried thing that also stands somewhere is refused; a position must be whole or absent; a thing with neither owner nor position is accepted — its adventure has not been entered yet.
- AC5 → one member may hold two characters; the same key twice in one campaign run is refused; undoing one step drops this table and leaves the earlier ones standing.
- Standing in for the brief's absent AC2: the table exists, provenance columns distinct from position columns, and removing a campaign run removes its objects.

## Order
Parallel: WI1, WI2, WI3 — all three bind to I1, which is fixed. Gates last.
