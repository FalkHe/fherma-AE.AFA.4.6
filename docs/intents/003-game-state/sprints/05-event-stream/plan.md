---
author: sprint
owner: agent
created: 2026-09-17
---
# Plan: Sprint 05 — an append-only, ordered, filterable transcript

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The transcript entity added to the existing game-state module as a declared table, with its module doc updated. | Every column's type, nullability and default · the five event types and the two visibilities · cost as an exact decimal, never a floating-point number · the cascade on the campaign run and the clearing on the actor · exactly two indexes and no sequence column | I1 |
| 2 | backend-python | The schema step that creates that table and its two indexes on an existing database and removes them again, chained after the previous step. | Its position in the chain · exactly the columns, constraints and indexes of I1 · undoing reverses it exactly | I1 |
| 3 | qa | Acceptance tests proving the five criteria against a real, migrated database. | See below | I1, green once WI1+WI2 land |

## Interfaces
- **I1 — the table, binding on all three.** Take the column table, every constraint and index with its final rendered name, the revision id `0006` / `down_revision = "0005"` and the `upgrade`/`downgrade` call order **verbatim** from `research.md → Interfaces`. Four points repeated because each has already caught somebody: a check takes the **short** name; **no column may be marked indexed on its own**, because the convention would render both composite indexes under the same name and they would collide; the stored cost is a decimal and must be read as one, never as a floating-point number; and the undo assertion **names** the step it undoes, never counts back one.

## Acceptance tests (qa → WI3)
- AC1 → several events written without timestamps of their own read back in write order by id alone. The database stamps every row in one transaction with the same time, so ordering must never touch the timestamp.
- AC2 → a read filtered to what the player may see skips a hidden event written between two visible ones, leaves no gap or placeholder, and the hidden row is still there on an unfiltered read.
- AC3 → each of the five types and each of the two visibilities is accepted, and anything else is refused.
- AC4 → three costs sum to the exact decimal total, and summing per turn gives the per-turn figure. No total is stored. Turn identifiers must be full-length values, because short ones come back padded.
- AC5 → the actor is cleared rather than cascaded when that member is removed, while removing the campaign run removes its events; undoing the named step drops this table and leaves the earlier ones standing.

## Order
Parallel: WI1, WI2, WI3 — all three bind to I1, which is fixed. Gates last.
