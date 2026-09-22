---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 04 — a second ingest replaces the corpus

| WI | Status | Note |
|---|---|---|
| 1 | done | no production code change; unit tests for AC3/AC4/AC5 in `test_ingest_service.py`, `database`-marked `test_reingest_replaces.py` for AC1/AC2/AC3/AC5, README re-ingest note; live: status 1750 @ 10:09:55 UTC → `app srd ingest` (1750 chunks, 507 719 tokens, USD 0.0102) → status 1750 @ 12:30:34 UTC, stored file unchanged, count = distinct citations = 1750; commits 849fb0b e53ae09 |

Status: `open | running | done | failed`

## Issues
- The brief predates the `## Task` template section; its `## Outcome` matches backlog row 04, so no `/fhit:backlog` repair was run.
- Architect's open question (is a differing row count acceptable AC1 evidence if upstream changed between runs?) decided by the sprint lead: yes — an upstream change shows as a git diff of the stored file, and count and diff moving together is exactly AC4; no change → AC1 as written.
- Branch carries `-r2`; `origin/sprint/004-04-reingest-replaces` is the stale 2026-09-16 chain.
- `glab` is signed in as `f4lkh3`; MR assignee is set to `st3ll4` explicitly.

## Backlog proposals
- Chunking does not disambiguate repeated heading paths; the current source has none, but a future source with two identical heading trails would make every ingest fail at commit (fail-safe: old corpus stays).

## Gates
Lint, backend suite (1011 passed), database-marked suite (149 passed) and frontend suite (65) pass. The frontend suite first failed at module install because the frontend image was stale after a dependency change merged to `main` (Goblin Pub look); `make build` fixed it — unrelated to this sprint.

## Verify
Round 1: approve — AC1–AC5 and D3 pass; verifier re-ran all three backend gates. Approval posted with the human's glab token, as before.
