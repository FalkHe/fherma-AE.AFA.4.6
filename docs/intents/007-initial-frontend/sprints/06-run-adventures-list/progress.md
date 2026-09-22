---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 06

| WI | Status | Note |
|---|---|---|
| 1 | done | adventures section + 4 route tests |
| qa | – | folded into WI1's route tests |

Status: `open | running | done | failed`

## Issues
- The brief assumed the disabled "Start adventure" explains itself on hover *and* focus; a disabled button takes no focus, so the explanation is hover-only and the same reason is stated in an always-visible line beside the section heading, where keyboard and screen-reader users reach it.
- An adventure the API marks `active` renders as the current row: D9 names no word for one already under way, and nothing in this intent can start an adventure. Worth deciding when adventure entry ships.

## Backlog proposals
- The seeded content has one campaign with one adventure, so the "Locked" and "Done" badges cannot be seen on the running site at all — a second, longer campaign would make the run screen reviewable end to end.

## Verify
Round 1: approve — no failed criteria. One non-blocking accessibility defect the verifier named (a stale aria-label on the ready state's disabled button) was fixed on the branch before merge; gates re-run green.
