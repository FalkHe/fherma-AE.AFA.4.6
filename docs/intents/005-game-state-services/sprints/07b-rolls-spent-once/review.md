---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/33
---
# Review: Sprint 07b — a roll is spent once, and the client sees what is awaited

## What changed

A roll on its own only says how the dice fell. Turning it into an outcome is a separate act: resolving a check
or a saving throw against a difficulty, which records the total, the difficulty and whether it succeeded.
Whether a roll passed is never written on the roll itself, only on what spent it. And a roll is spent once: not
twice, not in a later turn, not for another kind of thing. None of that sits in a column — it is read back from
the transcript, so there is nothing to keep in step.

## How to check it

- Resolving a check answers pass or fail and records the working for the DM.
- The same roll spent twice, in a later turn, for the wrong kind of thing, or against a difficulty outside 5 to
  30, is refused each time, and the refusal is recorded where only the DM sees it.
- A refused attempt does not burn the roll — a mistake costs the player nothing.
- The transcript read now also says what the game awaits: nothing, a roll asked for, or an answer.

## Heads-up

- The transcript read answers a slightly different shape now — the entries plus what is awaited, rather than
  just the entries. Nothing outside the backend reads it yet, and the generated client types are still phase 9's.
- A test from the knowledge-base work ran the whole suite inside one of its own tests, on a time budget the
  suite had outgrown; it now checks the same thing at a small fixed cost, which also took the routine test run
  from over two minutes to about ten seconds.
- This finishes the dice work. The two remaining sprints — handling objects, and fighting — can run in parallel.

Brief: docs/intents/005-game-state-services/sprints/07b-rolls-spent-once/brief.md

## Verdict

Round 1: approve — a dice roll now turns into a pass or fail against a difficulty, and it can be spent only once:
not a second time, not in a later turn, and not for something it was never rolled for, with every refusal
recorded where only the DM sees it and a refused attempt costing the player nothing. The transcript read now also
tells the client what the game is waiting for: nothing, a roll, or an answer.
