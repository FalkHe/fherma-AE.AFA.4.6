---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 09: Choices and rolls are buttons

## Task
Drive the waiting states from what the transcript says is awaited: a question stands with its answers as buttons, a called check stands with one "Roll {notation}" button, the composer is closed with "The Dungeon Master is waiting on one of those." or "The dice go first.", and picking or rolling writes the result into the transcript and continues the same turn with the thinking line back. A reload finds the same buttons still waiting.

## Outcome
A turn that stops on a question shows its answers as the only clickable things, and a turn that stops on a check shows one roll button whose press produces a dice result and continues the turn.

## Acceptance criteria
- AC1: Given a turn stopped on a question, when the screen renders, then its answers are buttons beneath the question, the composer is closed with its line, and nothing else sends.
- AC2: Given a picked answer, when sent, then it appears as the player's own row and the thinking line returns until the turn ends.
- AC3: Given a turn stopped on a check, when the screen renders, then "{ability} ({skill}) · DC {n}" stands with one roll button naming the notation and the composer closed with its line.
- AC4: Given the roll button pressed, then the button is replaced by the dice chip with breakdown, total and made-it/missed mark, and the turn continues.
- AC5: Given a closed browser while a question or roll waits, when the screen is reopened, then the same buttons are waiting.

## Decisions
← D2, D6

## Assumptions
- What is waiting is read from the transcript, never from a turn's response.
- The server rolls; the player never types a number.

## Out of scope
Free-typed answers while a question waits (← D2) · the failure line (10).
