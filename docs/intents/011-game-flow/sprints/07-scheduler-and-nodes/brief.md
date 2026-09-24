---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: draft
---
# Sprint 07: One rule for what happens next

## Task
Implement the single scheduler that reads the saved turn state and a freshly loaded situation and selects exactly one next effect in a fixed order — ending the run, an unresolved hit, a player request or answer, the current action, fight order, queued reactions, owed narration, turn closure — and implement the five worker behaviours (schedule, decide, execute, pause for the player, narrate) that each carry out one effect and hand control back. The scheduler also carries the guard against prompt injection in the player's text.

## Outcome
A table of turn states each selects the documented next effect, and closure is refused while any obligation remains.

## Acceptance criteria
- AC1: Given an unresolved hit, then only its damage flow is selected, never another actor or turn closure.
- AC2: Given a downed hero, then run completion is selected before anything else.
- AC3: Given an admitted round, then each eligible hostile is selected exactly once and downed, absent or friendly creatures are skipped; the hero side wins an initiative tie.
- AC4: Given an unanswered request, then the player pause is selected; given a stale answer, it is rejected; given a resume, nothing was saved or rolled before the pause.
- AC5: Given a player text matching the injection guard, then it is refused in the Dungeon Master's voice without a model call.

## Decisions
← intent §6, §7; AC "every eligible hostile acts according to the combat cursor"

## Assumptions
- Eligibility is recomputed from the situation after every change; reactions are consumed head-first.
- One table-driven test is the whole test budget for the scheduler; one test per node boundary.

## Out of scope
Wiring the behaviours into a graph, the turn endpoint.
