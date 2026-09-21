---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
stage: done
---
# Progress: Sprint 06b

| WI | Status | Note |
|---|---|---|
| 1 | done | `use_exit`: move, adventure end, game finish, recorded refusal |
| 2 | done | module doc and README; sections renumbered |
| qa | done | 2 acceptance tests, both database-marked |

Status: `open | running | done | failed`

## Issues

- The second half of the split sprint 06; 06a is merged. `use_exit` gets no route — phase 8's tool layer is its
  only caller — so every criterion is a database test over the service.
- Carried from 06a's verification: a test taking a scratch-database fixture must carry the `database` marker, or
  it lands in the engine-free suite and skips silently. Stated in this plan's qa section for that reason.

- qa disclosed reading `playthrough/errors.py` briefly while orienting, which its brief put off-limits. At that
  point the file held only earlier sprints' error classes and nothing from it reached the tests; the domain code
  it asserts comes from the plan. Recorded rather than acted on.

## Backlog proposals

<none yet>

## Verify

Round 1: changes-requested — AC3 and AC4b OK; AC2's behaviour is right (the verifier read the refusal back from a
second connection and found it durable) but its test is not: both refusal tests read through the same session
that wrote the row, where a flushed-but-uncommitted row is visible anyway. Deleting the commit in the refusal
path leaves the database suite fully green, so the crux of I3 is unprotected.

Round 2: approve — AC2's guard now reads the refusal record, the unchanged world and the player's silent
transcript through an engine the test builds itself on the scratch database after the raise. The verifier
confirmed `git diff` over `backend/app/` is empty since round 1, then stripped the commit from the refusal path
itself and watched AC2 fail on exactly that assertion while AC3 stayed green. Gates: lint, 835 engine-free,
53 frontend, 56 database.
