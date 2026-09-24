---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/72
---
# Review: Sprint 01 — Checks name their ability and skill as data

## What changed
Every hidden discovery and every fixture action in an adventure now states which ability and, where it applies, which skill the check uses, next to its difficulty. The Greenhollow adventure carries these for all six of its checks: both hidden clues are Wisdom (Perception), and the thorn screen and the wool sack each offer a Dexterity way by hand and a Strength way with a blade. An adventure that leaves the ability out is refused when the content is validated. The rules layer can read a check straight from those fields, and a passive check now records the skill it used. Play itself is unchanged: the Dungeon Master still calls the same checks the same way.

## How to check it
- Validate the shipped content: it passes, and every hidden clue and fixture action shows an ability beside its difficulty.
- Remove the ability from one clue in a copy of the adventure and validate it: the validation names the missing field and fails.
- Play a turn in the browser: nothing about rolling, questions or narration behaves differently.

## Heads-up
The ability assigned to each Greenhollow fixture check was taken from its own wording ("by hand" is Dexterity, "with a blade" is Strength); no author confirmed them.

Brief: docs/intents/011-game-flow/sprints/01-structured-checks/brief.md

## Verdict
Round 1: approve — every hidden clue and fixture action in Greenhollow states its ability and, where it applies, its skill beside the difficulty; validation passes on the shipped adventure and refuses one with the ability left out; the rules layer reads those fields directly and nothing about playing a turn changes.
