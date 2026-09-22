---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 01: The terminal game knows who acts, remembers the table, marks the run under way

## Task
Resolve the acting hero from the signed-in player and the run instead of requiring it as an argument, make the Dungeon Master's memory belong to the run itself so a session can be quit and rejoined where it stopped, and move the run from "ready" to "under way" the moment its first narration is written. Scope is the game and playthrough services plus the terminal command; no network route, no screen.

## Outcome
Playing two turns in the terminal without naming a hero works, quitting and replaying the same run continues where it left off with a pending question still pending, and the run then reads as in progress.

## Acceptance criteria
- AC1: Given a run with the ready-made hero seated, when the terminal game is started naming only the run, then the hero acts without an actor argument; the old override still works for debugging.
- AC2: Given a session quit while the Dungeon Master waits for an answer, when the same run is replayed, then the same question is still waiting and the answer continues that turn.
- AC3: Given a run in "ready", when its first narration is written, then the run reads as in progress on the dashboard read; a later narration leaves it unchanged.
- AC4: Given a run that has never been played, when read, then it is still "ready".

## Decisions
← D6, D9

## Assumptions
- The Dungeon Master's memory thread is the run: no session concept, no new table, and the history grows for the life of the run untrimmed.
- The acting hero is the player's own character in that run; the ready-made hero counts as theirs.
- The long-unused "activate run" step is what the first narration calls; nothing else flips the state.

## Out of scope
Any network route · cost recording (02) · anything on screen.
