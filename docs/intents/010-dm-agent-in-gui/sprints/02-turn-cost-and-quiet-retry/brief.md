---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 02: Each turn's cost is recorded, and a model hiccup no longer loses the turn

## Task
Sum the token and cost figures of every model call a turn makes and store them on that turn's narration, and route the Dungeon Master's narration call through the shared model seam so it gets the same quiet retry and error classification every other model call already has. Nothing displays the cost — the developer drawer is a later intent.

## Outcome
After a terminal turn, the run's recorded cost is greater than zero and grows with each turn, and a model call that fails once still ends in a narration.

## Acceptance criteria
- AC1: Given a completed turn, when its narration entry is read from the transcript, then it carries token counts and a cost above zero covering every model call of that turn.
- AC2: Given a run of several turns, when its cost is summed from the transcript, then the sum equals the per-turn figures added up.
- AC3: Given a model call that fails once with a retryable error, when the turn runs, then it completes with a narration and no error reaches the player.
- AC4: Given a model call that fails permanently, when the turn runs, then the turn ends with the classified error and everything recorded before it stays.

## Decisions
← D5, D8

## Assumptions
- The shared seam gains an async, tool-aware twin of its retry; the existing synchronous entry point is untouched.
- The per-call timeout stays at one minute and a turn may make several calls, so there is no server-side turn deadline — the two-minute give-up lives on the player's screen.
- Cost is recorded per turn and summed per run from the transcript, as the brief's grading asks; no separate ledger.

## Out of scope
Showing cost, model, temperature or tone anywhere (← D8) · the network route (03).
