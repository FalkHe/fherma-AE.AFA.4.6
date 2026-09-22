---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 07: Taking a turn

## Task
Add the composer, its send and the turn in flight: the player's words appear at once under the hero's name, the composer closes with "The Dungeon Master has the floor.", the thinking line sits at the foot while the turn runs, everything recorded during the turn appears as it happens, and the composer opens again with "What do you do?" when the turn is finished and nothing is pending. Live refreshing rides the existing notice stream and re-reads the transcript.

## Outcome
Writing an action on the play screen shows it in the transcript, then the thinking line, then dice and narration, and the composer is usable again afterwards.

## Acceptance criteria
- AC1: Given an open turn, when the player sends words, then their row appears at once and the composer closes with the in-voice line.
- AC2: Given a turn in flight, when the game records a roll or a system line, then it appears above the thinking line within a few seconds, before the narration.
- AC3: Given a turn that ends with nothing pending, when the narration lands, then it appears whole and the composer reopens.
- AC4: Given a reload during a turn, when the screen loads, then everything recorded so far shows and the thinking line is present only while the turn is still in flight.
- AC5: The notice stream reconnects on its own after it closes.

## Decisions
← D2, D3

## Assumptions
- A notice tick means only "something is new"; the client re-reads the transcript, so entries lag about two seconds and nothing streams word by word.
- What is on screen is driven by the transcript, not the turn's response.

## Out of scope
Choice and roll buttons (09) · long-wait wording and failure (10) · the opening turn (08).
