---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: running
---
# Progress: Sprint 04 — a second ingest replaces the corpus

| WI | Status | Note |
|---|---|---|
| 1 | running | |

Status: `open | running | done | failed`

## Issues
- The brief predates the `## Task` template section; its `## Outcome` matches backlog row 04, so no `/fhit:backlog` repair was run.
- Architect's open question (is a differing row count acceptable AC1 evidence if upstream changed between runs?) decided by the sprint lead: yes — an upstream change shows as a git diff of the stored file, and count and diff moving together is exactly AC4; no change → AC1 as written.
- Branch carries `-r2`; `origin/sprint/004-04-reingest-replaces` is the stale 2026-09-16 chain.
- `glab` is signed in as `f4lkh3`; MR assignee is set to `st3ll4` explicitly.

## Backlog proposals
- Chunking does not disambiguate repeated heading paths; the current source has none, but a future source with two identical heading trails would make every ingest fail at commit (fail-safe: old corpus stays).

## Verify
