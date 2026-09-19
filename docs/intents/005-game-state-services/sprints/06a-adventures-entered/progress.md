---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
stage: done
---
# Progress: Sprint 06a

| WI | Status | Note |
|---|---|---|
| 1 | done | `enter_adventure`, two refusals, two position statements; one round for the rollback |
| 2 | done | the entry route and its wire shape; found the rollback defect |
| 3 | done | module doc and README |
| qa | done | 3 acceptance tests |

Status: `open | running | done | failed`

## Issues

- **Sprint 06 was split into 06a and 06b** at the mechanic boundary, applying the precedent the product owner set
  for sprint 05 rather than asking again: entering an adventure and using an exit are two mechanics, and one
  sprint carried both plus a route, four error classes and two positioning statements. Research recommended the
  same line. 06b is issue #34, new; rows 08 and 09 now depend on 06b.
- Research raised one product-visible point: with the shipped one-adventure campaign a second entry always meets
  "nothing left to enter" first, so the "one is already active" refusal is unreachable until a campaign authors
  two or more adventures. Both refusals are in the approved criteria, so both ship; the second is tested against
  a fixture campaign. Flagged in `review.md`.
- Called, agent-level: `finish_campaign_run` stays inlined in 06b's `use_exit` rather than becoming a public
  function before a second caller exists.

- **A defect the route work item caught, not the tests.** `enter_adventure` rolled the whole session back before
  raising its "one is already active" refusal, which expires every object the *caller* had loaded — the next plain
  attribute read then fails. It now undoes only the speculative insert, through a savepoint, and a regression test
  pins that a caller's objects stay readable after the refusal. The verifier recorded the same hazard against
  05b's `latest_event_id`, which also rolls back; this is the pattern to follow there.

## Backlog proposals

- A test that takes the scratch-database fixture without the `database` marker lands in the engine-free suite and
  skips whenever Postgres is absent. Nothing catches that today; a `conftest` check could refuse the combination.
- 05b's `latest_event_id` expires the caller's ORM objects on every poll. Harmless for the stream's own session,
  a hazard for any later caller that shares a request session.

## Verify

Round 1: changes-requested — the behaviour is right (the verifier drove it against a real database and watched
the world land correctly), but AC1's positioning test takes the scratch-database fixture without the `database`
marker, so it is excluded from `make backend-test-db` and runs instead in the engine-free suite, where it skips
without a Postgres. It passed only because the dev stack happened to be up. Second gap: nothing pins that a
different adventure's cast stays unpositioned, though the two-adventure fixture is already in the file.

Recorded from that pass: 05b's `latest_event_id` should **not** adopt this sprint's savepoint pattern — its
rollback is load-bearing, releasing the read transaction between stream polls. Its own hazard (expiring a
caller's objects) is real but wants a different fix, and a backlog line of its own.

Round 2: approve — the marker fix moves AC1's positioning test into the database suite (3 collected there, none
in the engine-free one), and the verifier swept all 42 scratch-database tests in `backend/tests/` to confirm this
was the only one missing it. It then mutated the two position statements and the cast filter, and watched each
check fail; the isolation assertion catches a leak the single-adventure Greenhollow test cannot see. No
production code changed in this round, so round 1's confirmations stand. Gates: lint, 828 engine-free,
53 frontend, 48 database.
