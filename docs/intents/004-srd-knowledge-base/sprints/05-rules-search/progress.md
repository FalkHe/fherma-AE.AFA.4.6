---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: running
---
# Progress: Sprint 05 — rules search

| WI | Status | Note |
|---|---|---|
| 1 | running | |

Status: `open | running | done | failed`

## Issues
- The brief predates the `## Task` template section; its `## Outcome` matches backlog row 05, so no `/fhit:backlog` repair was run.
- Architect found that main embeds each passage body without its heading, so a spell's name lives only in `heading_path` and "fire bolt" ranks around 47th. Sprint lead decided to embed the heading trail with the body in `ingest` and re-ingest once (about one cent): it is the least effort way to make AC4's spell question pass and the number sprint 06 measures should be measured on the final embedding. Stored `text` stays the body, so the reported token count understates by roughly 5 %.
- `score` is the raw cosine distance (lower is closer), not the stale branch's similarity, because sprint 06's approved brief thresholds a distance.
- Branch carries `-r2`; `origin/sprint/004-05-rules-search` is the stale 2026-09-16 chain, used as porting reference.
- `glab` is signed in as `f4lkh3`; MR assignee is set to `st3ll4` explicitly.

## Backlog proposals

## Verify
