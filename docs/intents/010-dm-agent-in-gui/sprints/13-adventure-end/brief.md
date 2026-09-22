---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 13: The adventure's ending, and the way back

## Task
Recognise the adventure's end from the transcript, close it with "Here ends {adventure}", remove the composer entirely and offer the single "Back to {campaign}" button; on the run screen a finished adventure reads "Done" with "Read it back", which reopens the closed transcript exactly as it stands.

## Outcome
Finishing an adventure shows the ending narration, the end marker, no composer and one button back to the lobby, where the adventure reads "Done" and "Read it back" reopens it unchanged.

## Acceptance criteria
- AC1: Given the Dungeon Master completes the adventure, when the transcript refreshes, then the ending narration is the last entry, the marker follows it, the composer is gone and the button shows.
- AC2: Given the button pressed, then the run screen opens with that adventure marked "Done" and "Read it back".
- AC3: Given "Read it back", when pressed, then the play screen opens read-only with the whole transcript, the marker and the button, and no composer.
- AC4: Given a further adventure, when the run screen is opened, then it carries "Start adventure" as the next.

## Decisions
← D11, D12

## Assumptions
- The end is read from the transcript's own completion marker, never computed in the browser.
- A finished adventure is never reopened for play.

## Out of scope
What a fully finished campaign shows on the lobby (proposal) · replaying an adventure (← D11).
