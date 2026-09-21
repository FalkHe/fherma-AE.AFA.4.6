---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/35
---
# Review: Sprint 08b — items move between the floor, a pack and a container

## What changed

Items can be picked up, put down and handed over — only between things standing in the same scene. A sack on the
floor can be looted, so Greenhollow's stolen fleeces finally come out of the wool sack; an item another creature
holds still cannot be taken, because looting a container is not picking a pocket. Using an item exists as a
placeholder and refuses everything, nothing in the adventures being consumable yet.

## How to check it

- Picking up the bent horseshoe puts it in the character's hands; putting it down leaves it in that scene.
- Handing an item to someone in the same scene works; reaching into another scene does not.
- A fleece comes out of the wool sack. The goblin chief's cleaver does not come out of his hands.
- Using any item is refused as not consumable, and nothing moves.
- Picking something up spends the creature's action; putting something down does not.

## Heads-up

- Both of your rulings shipped: the sack is lootable, and dropping is free. The second is what makes
  pick-up-then-put-down work inside a single turn.
- Using an item refuses everything because an item cannot yet be *written* as consumable — the content schema
  has no such field. The shape is settled so consumables arrive later as authored content plus one branch.
- That finishes the object mechanics. One row is left in this phase: fighting.

Brief: docs/intents/005-game-state-services/sprints/08b-inventory-moves/brief.md

## Verdict
