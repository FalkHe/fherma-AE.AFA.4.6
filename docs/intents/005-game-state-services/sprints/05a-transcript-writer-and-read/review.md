---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/28
---
# Review: Sprint 05a — the transcript records and reads back

## What changed

A game now has a transcript, and one single way to write to it. Every entry says what kind it is — narration, a
player's action, a roll, a question, an error — and its content must match what that kind promises, or nothing
is written. Each entry is marked for the player or for the DM alone, and a player reads their transcript in
order, paging through it, never seeing what the DM keeps to itself.

## How to check it

- All twelve kinds are accepted with their own shape; a wrong shape, an unknown kind or an unknown audience
  writes nothing.
- A transcript reads oldest first, and asking for everything after a given entry continues where you left off.
- A DM-only entry sits between two visible ones in the table and is simply not in the answer.
- Someone else's game, and one that does not exist, both answer "not found".

## Heads-up

- You split sprint 05: this is the writer and the read; the cost report and the live "something is new" signal
  are 05b, which needs this one first.
- The transcript's order is the order of its entry ids, which works because one process mints them. A second
  process could let two entries made in the same moment come back swapped. That is written into the module
  documentation rather than fixed, and must be revisited before the app ever runs twice over.
- One check quietly skipped everywhere, because the tests could not see the documents they check. They can now.

Brief: docs/intents/005-game-state-services/sprints/05a-transcript-writer-and-read/brief.md

## Verdict

Round 1: changes requested — the safeguard meant to keep exactly one way of writing to the transcript only
recognises one of the two ordinary ways of writing one, so a later change could quietly add a second writer
and nothing would notice.
