---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: –
---
# Review: Sprint 02 — Each turn's cost is recorded; a momentary model failure is retried quietly, not fatal

## What changed
Every turn now records what it cost: the token counts and price of all the model calls that turn made are
stored on its narration, and a run's total is the sum of its turns. The Dungeon Master's own narration call
now takes the same path as every other model call, so a momentary failure is retried quietly instead of
ending the turn, and a real failure comes back as a named error rather than a raw one.

## How to check it
- Play a turn in the terminal, then read the run's cost: it is above zero and covers that turn's model
  calls (AC1).
- Play several turns and sum them: the run's cost equals the per-turn figures added up (AC2).
- A model call that stumbles once still ends in a narration, with nothing shown to the player (AC3).
- A model call that fails for good ends the turn with a named error, and the action and any rolls already
  made stay recorded (AC4).

## Heads-up
Nothing shows the cost yet — the developer drawer is its own later intent. Two small accounting limits:
the searches the Dungeon Master runs while looking up rules or memories are not counted, and a turn that
pauses for a question or a roll books its whole cost on the half that finishes it — the run total is still
exact, only the per-turn split is not.

Brief: docs/intents/010-dm-agent-in-gui/sprints/02-turn-cost-and-quiet-retry/brief.md

## Verdict
