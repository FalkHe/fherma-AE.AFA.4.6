---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
stage: draft
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| 3 | open | |
| qa | open | |

Status: `open | running | done | failed`

## Issues

- The brief contradicts itself: AC2 needs `GET …/campaign/{id}` while Out of scope forbids a single-run state read,
  and sprint 04's AC3 assumes the read exists. Called: a run row is not its state, so three routes ship and are
  documented. Flagged to the human in `review.md`.
- An unknown campaign id reuses `NOT_FOUND` rather than earning its own code; `ALREADY_STARTED` (409) is added to the
  shared code list for a repeated start.
- Newest-first sorts on `id DESC`, not `created_at DESC` — the ids are creation-ordered.

## Backlog proposals

- A carried instance belongs to a placement *instance*, so a placement with `count: 3` carrying something yields
  three carried objects. No shipped content does this yet; sprint 06 will meet it first.

## Verify
