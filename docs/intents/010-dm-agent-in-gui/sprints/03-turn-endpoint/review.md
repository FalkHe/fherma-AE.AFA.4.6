---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/63
---
# Review: Sprint 03 — A turn can be taken over the network

## What changed
A run can now be played over the network: one call takes a turn, and what the run is waiting for decides
what that call does. The caller cannot claim which kind of turn it is, and cannot supply a dice number:
the game rolls. The answer names the turn and what is waited on next.

## How to check it
From the interactive API page, against a run under way:
- Free words return when the turn ends; the transcript then holds the action, the rolls and the
  narration (AC1).
- While an answer is awaited, one of the offered choices continues the turn; anything else is refused,
  naming what is awaited (AC2).
- While a roll is awaited, asking for it makes the game roll; a number sent along is ignored (AC3).
- A retry after a broken turn carries on from the saved step, without rolling twice (AC4).
- No words on a fresh adventure gives a narration with no player row before it (AC5).
- A run you are not seated at is refused (AC6).

## Heads-up
The host's read timeout measured at 280 seconds or more, well above the two minutes a long turn may need,
so nothing is flagged (AC7). Answering a question now records the player's choice, which it never did
before. The transcript, never the reply, is the truth: a cut connection loses the narration, not what was
already recorded.

Brief: docs/intents/010-dm-agent-in-gui/sprints/03-turn-endpoint/brief.md

## Verdict
Round 1: changes requested — pressing "Try again" after a turn that broke answered the player with a server error whenever the run had nothing recorded under a turn yet, and that path shipped unproven.
Round 2: approve — retrying a turn that broke before anything had been recorded now carries on instead of answering with a server error, and the retry path is proven for real: the roll already made is not made again and a narration lands. A run can be played over the network — free words, a chosen answer, a rolled check, a retry after a break and an opening scene, with the game, never the caller, deciding which of these applies.
