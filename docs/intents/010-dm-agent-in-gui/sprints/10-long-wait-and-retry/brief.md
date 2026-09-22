---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 10: The long wait, and the turn that broke

## Task
Add the two waiting stages and the failure: the thinking line changes to "Still thinking. This one is taking its time…" after about 45 seconds, and at about two minutes — or on any turn that breaks — it becomes the in-voice failure line with "Try again", which picks the same turn up where it stopped, while the composer opens too. Returning to a turn that was in flight and never finished shows the same failure line.

## Outcome
A turn interrupted mid-flight shows the Dungeon Master's failure line with "Try again", every entry already recorded is still on screen, and both retrying and acting afresh work.

## Acceptance criteria
- AC1: Given a turn in flight for about 45 seconds, when the time passes, then the thinking line changes wording and nothing else moves.
- AC2: Given a turn in flight for about two minutes or a turn request that fails, when either happens, then the failure line appears as the Dungeon Master's row with "Try again" and the composer opens with "What do you do?".
- AC3: Given "Try again" pressed, when the turn resumes, then rolls and answers already recorded are not repeated and a narration lands.
- AC4: Given a turn that finished on the server after the give-up line, when the transcript refreshes, then its narration appears and the failure line goes.
- AC5: Given a player who left mid-turn, when they return, then the recorded entries show and, if the turn never finished, the failure line with "Try again".

## Decisions
← D4, D5, D6

## Assumptions
- Both timers live in the browser; the server has no turn deadline.
- "Try again" resumes the server's saved turn rather than resending the player's words.

## Out of scope
Automatic retries on return (← D6) · a leave warning (← D6).
