---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 02 — deterministic builder and saving

## What changed
A character described by name, race, class, alignment, point-buy scores, skills, equipment picks and story can now be saved to a run in place of the ready-made hero. The game derives every number itself: racial bonuses, hit points, armour class from armour and shield, saving throws, and each weapon's to-hit and damage. Picked gear becomes real carried items the character can attack with, and every field of the sheet survives combat.

## How to check it
- On the interactive API page, create a character on a fresh run with a body naming a Fighter with a legal 27-point spread: the answer carries hit points and armour class the body never stated, and the run reads ready.
- Send the same request with a score above 15 or a spread costing more than 27 points: it is refused with a message naming the ability or the cost.
- Create a character on a run with no body at all: Rosalind Thorn appears exactly as before.
- Attack with the new character's own weapon in a fight: the roll uses the weapon's to-hit and damage; Rosalind's knife still works as it did.

## Heads-up
- Point buy is our own rule (scores 8 to 15, 27 points); the SRD has none.
- A class default that reads "any simple weapon" or "any martial weapon" resolves to a mace or a longsword; a named pick can come with the chat sprint.
- Starting gear counts as proficient by definition; the prose proficiency lists are not checked.
- Two older tests asserting the exact shape of a saved character were updated for the wider sheet.

Brief: docs/intents/009-character-creation/sprints/02-deterministic-builder-and-save/brief.md

## Verdict
