---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 03: A turn can be taken over the network

## Task
Add the one network call that runs a turn for a run: free words when the turn is open, the chosen answer or the roll when the game is waiting for one, a retry that picks a broken turn up where it stopped, and an opening turn that carries no player words and writes no player row. What the run is currently waiting for decides which of these the server performs — never the caller's claim — and the answer names the turn and what is waited on next. Black-box acceptance tests belong to this sprint.

## Outcome
From the interactive API page, sending an action to a run under way returns when the turn ends, and the transcript afterwards holds the player's action, the rolls made and the narration.

## Acceptance criteria
- AC1: Given a run waiting for nothing, when free words are sent, then the transcript gains the player's row, the mechanics and the narration, and the answer says what is awaited next.
- AC2: Given a run waiting for an answer, when a choice is sent, then that turn continues; free words are refused with the error envelope naming what is awaited.
- AC3: Given a run waiting for a roll, when the roll is requested, then the server rolls, records it and continues the turn; a number sent by the caller is ignored.
- AC4: Given a turn that broke after a roll was recorded, when a retry is sent, then the turn resumes from the saved step, the roll is not repeated and a narration lands.
- AC5: Given a run whose adventure has just been entered and whose transcript is empty, when an opening turn is sent, then a narration appears with no player row before it.
- AC6: Given a run the caller is not seated at, when any turn is sent, then it is refused.
- AC7: The public host's proxy read timeout is measured and the result reported in the review; a value under two minutes is flagged.

## Decisions
← D1, D2, D4, D13

## Assumptions
- The transcript, never the response body, is the truth: a cut connection loses the narration, not what was already committed.
- A retry resumes the same memory thread from the server's last saved step; the one uncompleted step may run again.
- The turn holds one worker and one database session for its whole length; there is no background job.

## Out of scope
Anything on screen · streaming of any kind (← D3) · turn deadlines on the server.
