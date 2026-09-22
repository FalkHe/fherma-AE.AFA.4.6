---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 08: Start adventure, and the opening scene

## Task
Enable "Start adventure" on the current adventure row of the run screen: it enters the adventure and opens the play screen, which finds the transcript empty, shows "Nothing written down yet. The Dungeon Master is opening the book." and runs the opening turn at once. Entering happens once — returning later reads "Continue" and never re-enters.

## Outcome
Pressing "Start adventure" on a run that has never been played leads to the play screen, an empty transcript for a few seconds, and then an opening scene written by the Dungeon Master.

## Acceptance criteria
- AC1: Given a run with the ready-made hero and an adventure not yet started, when "Start adventure" is pressed, then the play screen opens with the scene name in the header and the empty line in the transcript, and the thinking line runs.
- AC2: Given the opening turn, when it ends, then a narration appears with no player row before it and the composer opens.
- AC3: Given an adventure already entered, when the run screen is opened, then the row reads "Continue" and never "Start adventure" again.
- AC4: Given a reload during the opening turn, when the screen loads, then what was recorded shows and the opening is not started a second time.
- AC5: Nothing asks for a character; the ready-made hero is enough.

## Decisions
← D1, D9, D13

## Assumptions
- The opening turn is an ordinary turn minus the player's row.
- An opening turn that broke is picked up by the retry of sprint 10.
- No dependency on intent 009.

## Out of scope
Character creation from the play screen (← D9) · the failure line (10).
