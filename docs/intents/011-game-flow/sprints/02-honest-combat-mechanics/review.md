---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/73
---
# Review: Sprint 02 — Fights with one roll per side, real criticals and a fallen hero

## What changed
A fight now opens with exactly two initiative rolls: the player rolls for the heroes' side when asked, the game rolls for the enemies, and the side that rolls higher acts first for the whole fight; the heroes win a tie. An attack now comes back as a clear hit, miss or critical, and on a critical the damage dice are doubled while the flat bonus counts once. A hero brought to zero hit points is treated as fallen everywhere: the scene no longer lists them as able to act, they cannot be picked as an attacker or a target, and their card reports them down.

## How to check it
- Start a fight in the terminal game: you are asked for one initiative roll, the enemies get one automatic roll, and on a tie the heroes act first.
- Land a natural 20: the damage line shows doubled dice with the bonus added once.
- Let the hero drop to zero: the scene description and the party read mark them down, and an attack aimed at or by them is refused.

## Heads-up
The settled fight order is not yet shown to the player; only the two rolls appear in the transcript. A fallen hero's card still shows zero hit points rather than the word "down"; that wording belongs to the party rail planned in intent 010.

Brief: docs/intents/011-game-flow/sprints/02-honest-combat-mechanics/brief.md

## Verdict
Round 1: changes requested — the player is no longer asked to roll their own initiative, the game rolls both sides silently where only the enemies' roll should be automatic; the detailed game rules documentation still says the player's click decides the heroes' roll and says nothing about doubled critical damage or the fallen hero's refusals.
