---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/60
---
# Review: Sprint 01 — The terminal game knows which hero acts, resumes a run where it was left, and marks it under way

## What changed
Playing a run in the terminal no longer asks who is acting: the campaign's own hero is taken from the
signed-in player and the run. The Dungeon Master's memory now belongs to the run rather than the session,
so a game can be quit and picked up exactly where it stopped, and a run stops reading as "ready" once its
first narration has been written.

## How to check it
- Start the terminal game naming only the run: the hero acts and no actor has to be named (AC1).
- Quit while the Dungeon Master is waiting for an answer, then play the same run again: the same question
  is still waiting and answering it continues that same turn (AC2).
- Play a fresh run: after the first narration it reads as in progress on the dashboard, and stays that way
  for the rest of the run (AC3).
- A run nobody has played yet still reads as ready (AC4).

## Heads-up
A run that has already ended is left alone rather than reactivated, so the closing narration of an
adventure cannot fail. The debugging overrides for actor and memory thread still work unchanged.

Brief: docs/intents/010-dm-agent-in-gui/sprints/01-terminal-actor-thread-activation/brief.md

## Verdict
Round 1: approve — playing a run in the terminal now works without naming a hero, quitting while the Dungeon Master waits leaves that same question waiting when the run is picked up again and the answer continues that turn, and a run reads as in progress from its first narration while one nobody has played still reads as ready.
