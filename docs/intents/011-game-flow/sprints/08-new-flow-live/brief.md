---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: approved
---
# Sprint 08: The new game flow goes live

## Task
Wire the five behaviours into one flow with a single router and run every turn through it from the existing turn request: translate an opening, a new action, a roll answer, a choice answer and a retry into its input, validate a resumed answer against the saved request instead of scanning the transcript, and prove the flow with four played-through scenarios — opening and conversation, an investigation across a roll pause and a restart, a move that changes the world, and a fight from initiative through damage to defeat.

## Outcome
Playing a run in the browser — opening, talking, rolling, fighting — works end to end on the new flow, with the same request body, the same waiting indicator and the same transcript entries as before.

## Acceptance criteria
- AC1: Given a player types an action, when the turn runs, then answer buttons, the roll button and the dice chip behave exactly as today.
- AC2: Given a roll request, when the server restarts before it is answered, then the same request is still waiting and resumes the same turn.
- AC3: Given the compiled flow, then it contains only the five behaviours and a single router.
- AC4: Given the four scenarios, then all four pass with scripted model decisions.
- AC5: Given a turn that breaks, then the composer stays closed and a retry resumes the saved turn.

## Decisions
← intent §8, §9.1–§9.6; AC "the turn API supports openings, actions, requests, resumes, and narration"; AC "the four end-to-end scenarios pass"

## Assumptions
- The turn request stays text-only and the waiting marker keeps its three shapes; the optional per-request status is not added.
- The old flow's files stay on disk this sprint so the change stays reviewable.
- The result is checked live on the hosted app before merge.

## Out of scope
Deleting the old flow (sprint 09), frontend changes.
