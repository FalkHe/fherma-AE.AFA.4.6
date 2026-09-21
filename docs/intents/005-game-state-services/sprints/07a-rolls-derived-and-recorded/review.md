---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: –
---
# Review: Sprint 07a — a roll is derived by the server and recorded as it fell

## What changed

The game can roll dice, and works out what to roll by itself. A roll comes from two things only — the kind of
roll and who is rolling: an attack uses the weapon's to-hit, damage its damage, a check or save the ability's
modifier, initiative Dexterity. The DM cannot hand it a number, and not by agreement: there is no way to pass
one in. The player can be asked to roll and answer later, the DM can roll outright or in secret, and a passive
check settles without dice. Every roll is recorded as it fell.

## How to check it

- Rolling from the command line prints the working: kind, actor, the formula it derived, the dice, the total.
- A made-up expression is refused and the message names it.
- Asking a player to roll records the request and the formula; answering records the dice as they fell, at the
  same visibility, so a secret roll stays the DM's.
- A passive check is recorded for the DM alone with no dice; asking a question is recorded too.

## Heads-up

- Sprint 07 was the biggest yet and I split it: this half derives and records a roll. Spending one — checks
  and saves passing or failing, a roll usable once, and telling the client what is awaited — is 07b.
- Your ruling that the SRD wins reached outside this sprint's module: content could author a difficulty of 1
  while the rules refused under 5, so the authoring floor is now 5 too. Nothing shipped breaks — Greenhollow's
  checks are 8 to 14 — but it is a content change inside a dice sprint.
- A monster's attack is named by the DM and derived from its stat block, as you decided.

Brief: docs/intents/005-game-state-services/sprints/07a-rolls-derived-and-recorded/brief.md

## Verdict
