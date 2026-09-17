---
author: sprint
owner: agent
created: 2026-09-17
updated: 2026-09-17
stage: done
---
# Progress: Sprint 04

| WI | Status | Note |
|---|---|---|
| 1 | done | `GameObject` added to the module, README extended, engine-free model tests |
| 2 | done | revision `0005` after `0004` plus its engine-free test — 8e35ece |
| 3 | done | 6 real-database acceptance tests, plus the fix below — 2fabecb, 74dbce0 |

Status: `open | running | done | failed`

## Issues
- **The approved brief has no AC2** — it runs AC1, AC3, AC4, AC5. Research checked this against the model attachment: every rule the model lists is covered by the four that are there, so nothing about refusing is missing. What has no criterion is the shape claim the previous sprint carried as its own first criterion. Decided rather than escalated: keep the approved numbering, and prove shape in the migration test plus one opening assertion in the acceptance suite. The brief is worth renumbering when it is next touched.
- The model attachment names the location rule twice under different names; the table section wins, and it is split into two checks so a failure says which rule fired.
- **This sprint broke the previous sprint's undo test and would have broken its own next sprint.** Both briefs word that criterion as "undo one step", which resolves against whatever the database's newest step is — so adding this sprint's step made the previous sprint's test undo *this* table and fail. Both tests now name the step they undo instead of counting back. Sprints 05 and 06 must keep naming it.
- One index merely repeats the leading column of a unique constraint. Kept, to stay literal to the approved model rather than hand sprint 06 a contradiction to document.

## Gates
`make lint` green · `make test` 639 backend + 53 frontend · `make backend-test-db` 26 passed.

## Backlog proposals

## Verify
Round 1: approve — every criterion probed against a live database rather than read off the SQL, including the one that mattered most: an item carrying any single fighting stat is refused, and health with no maximum is refused. No drift between the declared model and the migrated schema. The previous sprint's undo test was judged intact after the revision was named rather than counted.

MR: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/20
