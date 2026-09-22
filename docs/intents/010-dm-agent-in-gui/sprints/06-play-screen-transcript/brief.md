---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 06: The play screen shows everything that was recorded

## Task
Build the play screen at the run's address plus a segment: the header with the back link, adventure and scene, and the transcript rendering the four kinds of row, the dice chip, the scene dividers and the empty-transcript line, kept at the newest entry with the "Jump to the latest" pill when scrolled up, in the wording and layout of D12 including the narrow screen. On the run screen an adventure under way reads "In progress" with "Continue" leading here. Reading only — composer, buttons and live updating are later sprints.

## Outcome
Opening a run whose adventure is under way shows its whole recorded transcript in the D12 layout, and the back link returns to the lobby with nothing lost.

## Acceptance criteria
- AC1: Given an adventure under way, when the run screen is opened, then its row reads "In progress" with "Continue", and "Continue" opens the play screen.
- AC2: Given the play screen, when it loads, then the header shows "‹ {campaign}", the adventure title and "{scene} · saved as you go".
- AC3: Given a transcript with narration, player rows, system lines, dice, questions and a scene change, when rendered, then each kind appears as D12 draws it and system lines are worded from the values by the interface's own strings.
- AC4: Given an empty transcript, when rendered, then the empty line "Nothing written down yet…" shows.
- AC5: Given a long transcript, when it loads, then it sits at the newest entry; scrolling up shows "Jump to the latest".
- AC6: Given a narrow screen, when rendered, then the layout matches D12's narrow wireframe (party strip excluded until 11).
- AC7: Every string is an i18n key; the design's dark look applies.

## Decisions
← D1, D6, D12, D14

## Assumptions
- The whole transcript is read in one request, no paging.
- The run's transcript is one; adventure boundaries are markers inside it.
- "Start adventure" stays disabled until 08; a run played from the terminal is the reviewer's demo.

## Out of scope
Composer and turn (07) · party rail (11) · scene artwork (← D14).
