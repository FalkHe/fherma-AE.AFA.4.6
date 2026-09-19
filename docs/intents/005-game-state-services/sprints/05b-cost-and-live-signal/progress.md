---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
stage: draft
---
# Progress: Sprint 05b

| WI | Status | Note |
|---|---|---|
| 1 | done | `run_cost`, the cost command, the no-route guard |
| 2 | done | `latest_event_id`, the stream route, two settings |
| 3 | done | module doc sections for cost and the signal |
| qa | done | 2 acceptance tests |

Status: `open | running | done | failed`

## Issues

- **A shared test-fixture bug surfaced here and was fixed here.** `get_engine()` and `get_sessionmaker()` are
  cached, and the scratch-database fixture cleared only the settings cache — so the first test to build an engine
  pinned it for the whole run, aimed at a database later dropped. Nothing had built one in-process before this
  sprint's CLI tests, so the hole had never shown. The fixture now disposes and resets both caches.
- `make backend-test` now deselects the database-marked tests instead of relying on them skipping because no
  Postgres answers. That reliance made the gate depend on whether the developer's stack happened to be running.
- The second half of the split sprint 05; 05a landed first and is merged. Research predates it, so the plan tells
  implementers to read the landed code and treat the research as the contract.

## Backlog proposals

<none yet>

## Verify

Round 1: changes-requested — AC3 OK, including the proof that no address exposes cost and that the sums would
fail if they ran through floats. AC4 failed on test evidence: `latest_event_id` is monkeypatched in every
committed test, so neither its query nor its membership gate is ever executed; the verifier drove the real route
against a scratch database itself and it behaved correctly, which is the only reason this is a test gap rather
than a defect. Both harness fixes confirmed, the first by reproducing the old order-dependence on this branch.

Noted, not blocking: `latest_event_id` rolls back on every successful call, expiring every ORM object in the
session — harmless for the stream's own session, a hazard if a later caller shares a request session.
