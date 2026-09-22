---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: running
---
# Progress: Sprint 06 — relevance floor

| WI | Status | Note |
|---|---|---|
| 1 | done | `RELEVANCE_FLOOR = 0.60` (distance maximum) applied Python-side after order+limit; CLI prints `no relevant rule` exit 0 on `[]`; README section with the measurement table. Measured: worst in-corpus best 0.515 (half cover), best out-of-corpus best 0.686 (plasma rifle), no overlap, margin 0.085 both ways; other in-corpus 0.297–0.511, other out-of-corpus 0.81–0.87. Live: plasma rifle → `no relevant rule`; half cover → Combat › Cover first. Commits 0807bcd 36ba485 |

Status: `open | running | done | failed`

## Issues
- The brief predates the `## Task` template section; its `## Outcome` matches backlog row 06, so no `/fhit:backlog` repair was run.
- No architect agent: the human asked for least effort; the sprint lead wrote `research.md` from the stale branch and sprint 05's live numbers.
- The stale branch's floor (similarity 0.43) is not reused: the corpus was re-embedded with heading trails in sprint 05, so the value is re-measured today.
- Branch carries `-r2`; `origin/sprint/004-06-relevance-floor` is the stale 2026-09-16 chain, used as porting reference.
- `glab` is signed in as `f4lkh3`; MR assignee is set to `st3ll4` explicitly.

## Backlog proposals

## Gates
Lint, backend suite (1037 passed), database-marked suite (152 passed) and frontend suite (65) pass.

## Verify
