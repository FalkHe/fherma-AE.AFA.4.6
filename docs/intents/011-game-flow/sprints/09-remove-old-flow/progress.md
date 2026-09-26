---
author: sprint
owner: agent
created: 2026-09-26
updated: 2026-09-26
stage: running
---
# Progress: Sprint 09

| WI | Status | Note |
|---|---|---|
| 1 | done | character docstring, play-command fixtures, orphan smoke.md removed |
| 2 | done | docs/architecture.md rewritten, docs index row added |
| 3 | done | agent-graph.png deleted; backend/graph.png named in the intent no longer existed |
| 4 | done | lint green; 1258 unit tests green; name search clean; the opt-in database suite has 22 pre-existing failures reproduced on main |

Status: `open | running | done | failed`

## Issues
- The prompt-injection regex guard disappears with the old flow, so "security guard" in the requirement map now rests on ownership and authentication boundaries alone. Intent 011 lists the guard node under what is removed, so this is decided there and not reopened.

- The opt-in database suite (`make backend-test-db`) fails 22 of 189 tests with `NoResultFound` on item rows; an implementer reproduced the same failures on unmodified `main` in a separate worktree with its own Postgres, so they are not caused by this sprint. Recorded as a backlog proposal; the default suite that AC4 names is green.
- `docs/general/game-flow.v2.md` still linked the deleted `game-flow.md`; the two links now point at the game README and the examples document.

- Decision after verify round 1: the recovery for runs paused before sprint 08 is restored as clearly marked migration code rather than declaring those campaigns lost; it reads a stored checkpoint shape, not the old flow's code, so "one way the game works" still holds.

## Backlog proposals
- The database-marked suite fails on `main` (22 tests, missing item rows in the scratch database); a small fix-up sprint should restore it before it is relied on as a gate again.

## Verify
Round 1: changes-requested — scope/outcome: the legacy-checkpoint recovery for runs paused under the old flow was removed with the cleanup, so such runs are stuck; review.md claimed nothing visible changes.
