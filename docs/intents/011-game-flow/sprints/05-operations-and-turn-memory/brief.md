---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: draft
---
# Sprint 05: Every game action as one validated operation, remembered across restarts

## Task
Define the explicit workflow state kept for the active turn — turn frame, interpreted move, action in progress, fight order, outstanding player request, unresolved wound, queued reactions and narration progress — with the rule that turn-local state clears at turn end while fight order lasts until the fight ends. Build one registry of operation handlers covering player input, checks, world changes, combat and lifecycle; each validates its references against a freshly loaded situation before calling the rules layer and returns a typed result. Requests for a roll or a choice write the visible request entry before the pause and the answer entry after it, exactly as today.

## Outcome
An interrupted roll request and an active fight order restore unchanged after a restart, every operation kind has exactly one handler, and an operation naming something not in the current scene is refused before any change is made.

## Acceptance criteria
- AC1: Given an outstanding roll request and an active fight order, when state is saved and restored, then both come back identical; when the turn closes, only the fight order remains; when the fight ends, it is cleared.
- AC2: Given the list of operation kinds, then each has exactly one handler and none is orphaned.
- AC3: Given a stale or invented reference, then the operation is refused and no rules-layer change runs.
- AC4: Given an action whose roll is already used, then the same roll cannot be applied twice in normal flow.
- AC5: Given a roll request, then its visible entry still carries the ability, skill and difficulty the dice chip shows, and a question still carries its answers.

## Decisions
← intent §3, §4; AC "active requests, operation results, hits, rolls and combat order survive restart without workflow tables"; AC "no migration"

## Assumptions
- A hero's own requested roll may show its difficulty to the player, as the shipped dice chip already does; private means hidden facts, monster intent and the mapping from an answer button to an object.
- Internal state uses plain typed structures, not validation models; identifiers come from the project's existing id helper.
- New code lives beside the old flow, which keeps serving turns until sprint 08.

## Out of scope
Choosing which operation runs next (sprint 07), model calls (sprint 06).
