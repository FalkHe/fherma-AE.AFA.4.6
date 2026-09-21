---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/32
---
# Review: Sprint 07a — a roll is derived by the server and recorded as it fell

## What changed

The game rolls dice and works out what to roll by itself, from two things only — the kind of roll and who is
rolling. An attack uses the weapon's to-hit, damage its damage, a check or save the ability's modifier,
initiative Dexterity. The DM cannot hand it a number, and not by agreement: there is no way to pass one in. The
player can be asked to roll and answer later, the DM can roll outright or in secret, and a passive check settles
without dice. Every roll is recorded as it fell.

## How to check it

- Rolling from the command line prints the working: kind, actor, the derived formula, the dice, the total.
- A made-up expression is refused and the message names it.
- Asking a player to roll records the request and its formula; answering records the dice as they fell, at the
  same visibility, so a secret roll stays the DM's.
- A passive check is recorded for the DM alone with no dice; a question is recorded too.

## Heads-up

- Sprint 07 was the biggest yet and I split it: this half derives and records a roll. Spending one is 07b.
- Your ruling that the SRD wins reached outside this sprint's module: content could author a difficulty of 1
  while the rules refused under 5, so the authoring floor is now 5 too. Nothing shipped breaks — Greenhollow's
  checks are 8 to 14 — but it is a content change inside a dice sprint.
- A monster's attack is named by the DM, derived from its stat block, as you decided.

Brief: docs/intents/005-game-state-services/sprints/07a-rolls-derived-and-recorded/brief.md

## Verdict

Round 1: changes requested — nothing in the automated checks would catch it if answering a player's roll request
stopped using the formula the player was promised and worked one out fresh instead. That was proved by making
exactly that change and watching every check still pass.

Round 2: approve — the game works out every roll by itself, from the kind of roll and who is rolling, never a
number handed to it; and a roll the player was promised is answered with that very promise, confirmed by
breaking it on purpose and watching the new check catch it. Spending a roll, and the pass-or-fail that goes with
it, remains 07b as planned.
