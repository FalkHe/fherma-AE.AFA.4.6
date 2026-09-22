---
author: fhit:architect
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 07: review, save and the finished character

## Task
Close the loop in the frontend character module: the review screen that follows the conversation with the
full sheet laid out as delivered, its two buttons, and the save; and the character card the run screen's
player card shows afterwards, with the party line and the first adventure following from it.

## Outcome
After confirming at the review, the player lands back on the run screen, sees their character's card with
name, race, class, hit points, armour class and looks, the party reads "1 of 1 characters ready" and the
first adventure is next up.

## Acceptance criteria
- AC1: When the sheet is ready the review appears with name, race, class, level, alignment, hit points,
  armour class, speed, abilities with modifiers, skills, equipment, looks and backstory (← D9, D14).
- AC2: The buttons read "Looks right, save" and "Change something", with the line "Saving makes it final
  for this run."; "Change something" returns to the conversation and the sheet is unchanged (← D9, D16).
- AC3: Saving creates the character, returns to the run screen and shows the new state without a manual
  reload (← D14).
- AC4: The player card carries the character card — name, race and class, level, hit points, armour class,
  looks clamped to three lines — and no way to edit it; the party line counts the ready character (← D14,
  D15).
- AC5: A save that fails keeps the review on screen with the tavern's error line and lets the player try
  again (← D16).
- AC6: Every string is a translation key; one test per criterion, no snapshots, no browser suite.

## Decisions
← D9, D14, D15, D16

## Assumptions
- The run screen is refetched on return rather than listening for a live update.
- Asking to change something reopens the conversation where it stopped, with the review reachable again
  from the next reply that says the sheet is ready.
- A ready-made hero taken at the greeting reaches the same review screen, read-only wording aside.

## Out of scope
No edit mode after saving · no read-only sheet view, dropped with D14 · no adventure start · no second
character per run.

## Depends on
Sprint 06, and intent 007 sprint 05 for the party section the card sits in.
