---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: running
---
# Progress: Sprint 07

| WI | Status | Note |
|---|---|---|
| 1 | done | dashboard, run cards, empty state; home retired; round 2 restored two lost guard tests |
| qa | – | folded into WI1's route tests |

Status: `open | running | done | failed`

## Issues
- Sprint lead merged the architect's two work items into one: building the dashboard and retiring the old landing page are the same edit, and AC6 is only checkable once the new screen exists.
- Two copy calls decided rather than referred up: with no runs the greeting carries no counting subtitle and the invitation card states the message instead; and the card's meta line counts the adventure the party is *on*, so a fresh run reads "Adventure 1 of 8" rather than "0 of 8".
- `/dashboard` as a second guarded address is retired with the old module; `/runs/<id>` already proves the guard covers more than one address, and the two acceptance tests that deep-linked it now deep-link there.

## Backlog proposals

## Verify
