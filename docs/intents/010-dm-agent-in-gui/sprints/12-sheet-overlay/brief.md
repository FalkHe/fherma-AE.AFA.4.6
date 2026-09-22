---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 12: The full sheet over the transcript

## Task
Open the full sheet — ability scores with modifiers, hit points, armour class, race, class, level, appearance, backstory and what the hero carries — as an overlay from the party rail (card or narrow strip), closing back to play with nothing lost. It uses the data the rail already read.

## Outcome
Tapping the hero on the play screen opens a readable sheet over the transcript, and closing it leaves the transcript and any pending buttons exactly as they were.

## Acceptance criteria
- AC1: Given the rail, when a hero is tapped, then the sheet opens over the transcript with every listed field.
- AC2: Given the sheet open, when closed, then the transcript position, thinking line and any waiting buttons are unchanged.
- AC3: Given a turn that changed hit points or items while the sheet is open, when the next refresh lands, then the sheet shows the new values.
- AC4: Opening the sheet makes no new network request.

## Decisions
← D15

## Assumptions
- The sheet shows what the ready-made hero has today and grows on its own once created characters store more.
- Intent 009's character card should reuse this view.

## Out of scope
Editing anything on the sheet · the lobby's character card (009).
