---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/36
---
# Review: Sprint 09 — a fight happens entirely in the transcript

## What changed

Characters and monsters can fight, and a fight is not a thing the game stores anywhere. No encounter to open or
close, no turn order kept, no flag saying a fight is on: rolling for who goes first records two rolls and
nothing else, and striking and wounding are ordinary acts that work in any scene — an ambush is just an attack
during exploration. A blow is measured against what the target wears, and a wound is bound to the blow that
landed it, so nothing is hurt without a hit behind it.

## How to check it

- A roll reaching the goblin's armour hits; a natural 20 is a critical hit whatever the armour; less misses.
- Damage names the blow it follows and takes its target from there; hit points fall and stop at nothing.
- At nothing left the goblin is no longer alive; a character stays alive and is marked down instead.
- A blow that missed, one from an earlier turn, and one already paid out cannot be used again.
- One attack per creature per turn, and a monster's attack never asks the player to roll.
- After a whole fight, the database holds no table, column or stored value saying a fight happened — checked by
  listing them all, not by hunting for suspicious names.

## Heads-up

- A character at nothing left is marked *down* and no more. The rules have such a character *dying* and making
  death saving throws; none of that exists, nothing narrates it, and nothing ends a game whose character never
  gets up. That wants your decision before the narrating phase is built.
- This is the last sprint of the phase. Every change to the stored game now goes through a named mechanic.

Brief: docs/intents/005-game-state-services/sprints/09-fight-lives-in-the-transcript/brief.md

## Verdict
