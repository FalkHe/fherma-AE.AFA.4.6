---
author: fhit:architect
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 06: the creation page

## Task
Build the creation chat as a page of its own in a new frontend character module, reached from "Create
character" on the run screen: transcript, composer, the offered choices as buttons, and the live "your
sheet so far" panel with its step indicator beside it, collapsing under the composer on a narrow screen.
Add the leave dialog and the in-voice error line with its retry, all copy in translation keys.

## Outcome
Clicking "Create character" on a run opens its own page where the player talks to the Tavern Keeper, sees
each answer appear in the sheet panel beside the transcript, and leaving asks first.

## Acceptance criteria
- AC1: "Create character" on the run screen opens the creation page at its own address; the in-development
  dialog is gone from that button (← D14).
- AC2: The transcript shows the Tavern Keeper's and the player's turns; offered choices appear as buttons
  that send the same thing typing them would (← D14, D15).
- AC3: The sheet panel shows what is set and what is still empty, plus the step reached, and updates with
  every reply; on a narrow screen it is a collapsed strip that expands into the same list (← D14).
- AC4: Leaving or navigating away asks "Leave character creation? Nothing is kept — you would start over."
  with "Keep going" and "Leave"; leaving returns to the run screen unchanged (← D12, D16).
- AC5: A failed turn shows the tavern's error line inline with a retry, keeping the conversation on screen
  (← D16).
- AC6: Every string is a translation key; the tests are one per criterion, no snapshots, no browser suite.

## Decisions
← D12, D14, D15, D16

## Assumptions
- The page lives at the run's address plus a creation segment, so a reload lands back on the run screen.
- The page is a reload-loses-it surface: nothing is stored in the browser.
- The delivered dark look and the existing shell are reused as they stand.

## Out of scope
The review screen and the saved character card are sprint 07 · no streaming · no editing after saving.

## Depends on
Intent 007 sprint 05, the run screen with its party section, must be merged first.
