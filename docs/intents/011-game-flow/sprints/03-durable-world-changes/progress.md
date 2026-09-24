---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
stage: done
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | done | fixture outcomes persisted, typed results and refusals, use_item and scans removed |
| 2 | done | set_hostility, leave_scene, enter_next_adventure, finish_run |
| 3 | done | four record functions; game module has no commit or event append |

Status: `open | running | done | failed`

## Issues
- The spent-roll scan is kept until sprint 05 owns the roll cursor; only the acted-already gate and the damaged-hit scan go now.
- No qa agent, per owner's "reduce testing".

## Issues (gates)
- WI1 folded its tests into existing files instead of one new file; WI3 reported done before committing and needed a nudge. Gates passed first time.

## Backlog proposals
- Retired error codes (exit not available, roll required, already acted, item not consumable) still exist as enum members and HTTP mappings in the core error module; sprint 09's cleanup should drop them.

## Verify
Round 1: approve, no failed criteria.
