---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
stage: draft
---
# Progress: Sprint 02

| WI | Status | Note |
|---|---|---|
| 1 | done | two side rolls settled once, hero wins tie; old initiative tests deleted |
| 2 | done | typed attack/damage results, crit doubles dice only |
| 3 | done | one down rule for writes and reads; character read gained `down` on the wire |

Status: `open | running | done | failed`

## Issues
- Research raised two questions; both resolved by keeping today's behaviour: the settled fight order stays internal (nothing shows it to the player today), and a downed hero's card keeps showing 0 hp; "down" wording is intent 010's party rail.
- No qa agent, per owner's "reduce testing".

## Issues (gates)
- WI1 returned twice before committing because it ran tests in the background; its service edits were swept into WI2's commit, tests committed on a second nudge.
- Full suite round 1: two character tests built a character read without the new `down` field; fixed in one round. Wire change required regenerating the frontend client and one frontend fixture.

## Backlog proposals
- Show the settled initiative order and a "down" marker to the player once the party rail exists (intent 010 sprint 11).

## Verify
