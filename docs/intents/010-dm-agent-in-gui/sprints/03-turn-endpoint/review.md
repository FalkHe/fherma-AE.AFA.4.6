---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: –
---
# Review: Sprint 03 — An action, answer, roll, retry or the opening of a new adventure can be sent to the game over the network

## What changed
A run can now be played over the network: one call takes a turn. What the run is actually waiting for
decides what that call does — free words while the turn is open, the chosen answer or the roll while the
game waits for one, a retry that picks a broken turn up where it stopped, or the opening of a brand-new
adventure, which carries no player words and writes no player row. The caller cannot claim which of these
it is, and cannot supply a dice number: the game rolls. The answer names the turn and what is waited on
next.

## How to check it
- From the interactive API page, send free words to a run under way: the call returns when the turn ends,
  and the transcript then holds the player's action, the rolls made and the narration (AC1).
- While the game waits for an answer, send one of the offered choices: the turn continues. Send something
  else and it is refused, naming what is awaited (AC2).
- While the game waits for a roll, ask for it: the game rolls and records it. A number sent along is
  ignored (AC3).
- After a turn broke following a roll, send a retry: it carries on from the saved step, the roll is not
  made twice, and a narration lands (AC4).
- Open a new adventure with no words: a narration appears with no player row before it (AC5).
- Send a turn to a run you are not seated at: refused (AC6).

## Heads-up
The public host's read timeout was measured at 280 seconds or more — comfortably above the two minutes a
long turn may need, so nothing is flagged (AC7). Answering a question now records the player's choice in
the transcript, which it never did before; without it an answered question would have stayed waiting for
ever. A turn holds one worker for its whole length — there is no background job — and the transcript,
never the reply, is the truth: a cut connection loses the narration, not what was already recorded.

Brief: docs/intents/010-dm-agent-in-gui/sprints/03-turn-endpoint/brief.md

## Verdict
