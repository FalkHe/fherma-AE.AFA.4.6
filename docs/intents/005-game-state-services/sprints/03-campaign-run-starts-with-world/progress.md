---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
stage: done
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | done | service, errors, `ALREADY_STARTED`; id derivation sent back once |
| 2 | done | three routes, wire schemas, router registration, route tests |
| 3 | done | module README and playthrough doc §8 |
| qa | done | 3 acceptance tests; AC3 corrected after the id finding |

Status: `open | running | done | failed`

## Issues

- The brief contradicts itself: AC2 needs `GET …/campaign/{id}` while Out of scope forbids a single-run state read,
  and sprint 04's AC3 assumes the read exists. Called: a run row is not its state, so three routes ship and are
  documented. Flagged to the human in `review.md`.
- An unknown campaign id reuses `NOT_FOUND` rather than earning its own code; `ALREADY_STARTED` (409) is added to the
  shared code list for a repeated start.
- WI1 first derived the run id from `(user_id, campaign_id)` to make a repeat start conflict, which would have stopped
  a player from ever replaying a finished campaign and contradicted a guarantee intent 003 landed and tests. Sent back:
  fresh ULIDs, and the uniqueness guard reinterpreted as "one run instantiates its world exactly once". The phrasing
  that misled it came from this plan's own interface text, which is corrected.
- Newest-first sorts on `id DESC`, not `created_at DESC` — the ids are creation-ordered.

## Backlog proposals

- A carried instance belongs to a placement *instance*, so a placement with `count: 3` carrying something yields
  three carried objects. No shipped content does this yet; sprint 06 will meet it first.

## Verify

Round 1: approve — AC1-AC4 all OK. The verifier re-ran the gates, checked the list scoping and the
foreign/unknown equivalence against a real database, and confirmed no existing test lost coverage (the four
touched test files are pure additions).

Non-blocking notes it raised, for whoever picks up the next sprint: the `IntegrityError` catch in
`start_campaign_run` is wider than the duplicate-key case it names, and is the pattern later sprints will copy;
`list_versions(...)[-1]` raises on a campaign directory with no version in it; `playthrough/service.py` imports
`content.errors` and `content.schemas` alongside its `service.py`, slightly wider than the module boundary rule.
