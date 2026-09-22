---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 01 — character sheet and SRD options

## What changed
The game now knows every race, class, skill and alignment a player may pick, and the numbers each of them fixes: ability bonuses and speed per race, hit die, saving throws, skill picks and starting-equipment choices per class, plus the armour and weapon tables and our own point-buy rule. It also defines the full character sheet a created hero is described by. Nothing is visible in the app yet; this is the ground the Tavern Keeper will stand on.

## How to check it
- Run `app character options` in the backend container: it lists 9 races with speed, size and bonuses, then 12 classes with hit die, saving throws, skill count and every equipment choice as "(a) … | (b) …".
- Spot-check one class against the SRD text: Barbarian shows hit die d12, saves strength and constitution, and "(a) a greataxe | (b) any martial melee weapon".
- A sheet naming a race, class, alignment or skill outside the SRD lists is refused.

## Heads-up
- Point buy (costs 8 to 15, 27 points) is our own rule; the SRD has no ability-score method. The module README says so.
- The SRD gives the Rogue's last equipment line no alternative, so it is a single fixed choice; the Net weapon has no damage in the SRD and is recorded with a zero die.
- Only the two story skills will be asked in chat; the skills a class grants itself are recorded here for auto-fill (D18).

Brief: docs/intents/009-character-creation/sprints/01-character-sheet-and-srd-options/brief.md

## Verdict
