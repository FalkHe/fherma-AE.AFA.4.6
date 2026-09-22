---
author: fhit:architect
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 03: the Tavern Keeper in the terminal

## Task
Give the `character` module its own small agent — graph, prompt and tools — modelled on the existing game
agent: the builder functions of sprint 02 are its tools, the sheet so far is its state, the checkpointer
keeps the thread. Add the interactive terminal command `app character create` in the shape of `app game
play`, carrying the shortest complete path: greeting, the ready-made offer, free words turned into race
and class, name, looks and backstory, a suggested ability set, the review and the save.

## Outcome
In the terminal a player says "a sneaky halfling burglar", answers a handful of questions, sees the full
sheet, confirms, and the run holds that character.

## Acceptance criteria
- AC1: The agent opens by naming the campaign's ready-made hero as one way out and building your own as
  the other; taking the hero goes straight to the review and the save (← D11, D14).
- AC2: Free words are turned into one of the nine races and twelve classes and written down only after the
  player agrees; if either is missing the agent asks with a few fitting suggestions (← D1, D4).
- AC3: Every number on the sheet comes from a tool call, never from the agent's own words (← D1).
- AC4: Before saving, the whole sheet is shown and the player confirms; saving is announced as final for
  this run (← D9).
- AC5: Quitting before the save keeps nothing — a new start begins at the greeting (← D12).
- AC6: The agent calls itself Tavern Keeper in its prompt and its lines only; no identifier carries the
  name, and its wording is in the tavern's voice, errors included (← D15, D16).

## Decisions
← D1, D2, D3, D4, D9, D11, D12, D15, D16

## Assumptions
- Nothing is written until the player confirms, so an abandoned conversation needs no cleanup.
- The prompt lives with the character module and is versioned like the existing ones.
- Tests drive the graph with a scripted model, not a real one; one test per criterion.

## Out of scope
No point buy by hand, no dice for scores, no alignment, no skills, no equipment choices, no retold
backstory — all sprint 04. No web surface, no streaming.
