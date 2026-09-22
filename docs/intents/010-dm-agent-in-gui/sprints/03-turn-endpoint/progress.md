---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
stage: draft
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | done | turn kind derived from the run's real state; player row written on answer; open turn id reused |
| 2 | done | turn route, shapes, error mapping and regenerated typed client |
| 3 | done | six acceptance tests through the route; host read timeout measured at >=280s |

Status: `open | running | done | failed`

## Issues
Research found that nothing wrote the player's row when a question was resumed, so an answered question would have stayed awaited for ever; WI1 owns the fix. The terminal minted a fresh turn id per leg, splitting the open-turn window and the per-turn cost; the network call reuses the open turn's id instead.

## Backlog proposals
The acceptance tests drive the route with the turn engine stubbed, so they prove the wire and the error envelope; the engine's own behaviour is covered by its unit tests.

## Verify
Round 1: changes-requested — AC4: the retry path answered with a server error whenever the run had no turn-bearing event yet, and was never genuinely tested; review.md over the word cap.
