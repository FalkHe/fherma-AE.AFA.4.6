---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: draft
---
# Sprint 03: Lasting world changes owned by the rules layer

## Task
Persist a successful fixture outcome in world state; give scene departure, hostility change, entering the next adventure and run completion for victory, defeat and authored ending their own operations with typed results; let exit use record which turn it belonged to and return a typed result; and move the recording of player actions, answers, mechanic outcomes and narration into the rules layer so nothing outside it saves anything. Remove the always-refusing item use and the scans that search past events for spent rolls, damaged hits and creatures that already acted.

## Outcome
Lifting the thorn screen leaves the way open after a reload, and no code outside the rules layer commits anything.

## Acceptance criteria
- AC1: Given a successful fixture action, when the run is reloaded, then the fixture is still open.
- AC2: Given the final adventure is completed or the hero is defeated, then the run records the matching ending.
- AC3: Given a player action, answer or narration, then the rules layer records it with its turn, and the game layer holds no save of its own.
- AC4: Given an expected refusal such as an unreachable item, then it comes back as a typed refusal; only ownership, identity, lifecycle and infrastructure failures raise.

## Decisions
← intent §1.6, §1.7, §1.8, §1.9; AC "expected refusals are typed results"

## Assumptions
- Fixture state is a flag plus the authored outcome kept on the object; hostility is a field on the creature; both live in existing state storage, so no migration.
- Dropping the duplicate-action guard makes the old flow slightly more permissive until sprint 08 replaces it.

## Out of scope
Graph state, handlers, decisions.
