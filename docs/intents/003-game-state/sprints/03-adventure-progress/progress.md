---
author: sprint
owner: agent
created: 2026-09-17
updated: 2026-09-17
stage: done
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | done | `AdventureRun` added to the module, README extended, engine-free model tests — 8ab029b |
| 2 | done | revision `0004` after `0003` plus its engine-free test — 0a2efb5 |
| 3 | done | 5 real-database acceptance tests, one per criterion — f6369bf, tightened after verification |

Status: `open | running | done | failed`

## Issues
- Unlike sprint 02's, this brief's undo criterion is literally testable: the fixture leaves the scratch database at head, so undoing one step resolves to the previous one. It must not be asserted in a test that already undid the same database.

## Gates
`make lint` green · `make test` 600 backend + 53 frontend · `make backend-test-db` 20 passed.

## Backlog proposals

## Verify
Round 1: approve — all five criteria met, the one-in-progress rule confirmed as a partial unique index against a live database, constraint names correct, and the declared model compared to the migrated schema with no drift.
Two non-blocking observations from that round were fixed anyway: the duplicate-adventure test could have passed with its constraint removed, because both rows also tripped the one-in-progress index; and the "no scene column" check matched an exact name, so `scene_id` would have slipped past.

MR: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/19
