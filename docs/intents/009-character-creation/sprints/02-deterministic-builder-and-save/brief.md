---
author: fhit:architect
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 02: deterministic builder and saving

## Task
Add the maths of character creation to the `character` module as plain functions: point buy, a suggested
set per class, scores rolled through the existing dice seam (`playthrough/dice.py`), racial bonuses,
modifiers, hit points, armour class from armour and shield, and each weapon's to-hit and damage. Then let a
finished sheet reach the table: playthrough gains a full sheet type and a wider character state (today's
model drops unknown fields on the first hit), `create_character` accepts the sheet and writes picked gear as
carried item rows holding their attack numbers in state, the attack lookup reads those, and the character
route accepts an optional body.

## Outcome
Posting a finished sheet to a run creates that character instead of the campaign's ready-made hero, with
hit points, armour class and carried gear the sheet did not have to spell out in numbers, the run turns
ready, and the character can attack with a picked weapon.

## Acceptance criteria
- AC1: Point buy accepts a legal spread and refuses an illegal one, naming what is wrong (← D5).
- AC2: Rolled scores come from the game's own dice, never from a caller-supplied number, and are
  reproducible in a test through the existing dice seam (← D5).
- AC3: Hit points, armour class, modifiers, saving throws and weapon to-hit and damage are derived from
  race, class, scores and equipment, not accepted from the caller (← D1, D17).
- AC4: Every field of the sheet survives a hit: the character state model carries them all and the damage
  mechanic writes them back unchanged (← D9).
- AC5: Picked equipment is saved as carried items; an attack naming a picked weapon resolves its to-hit and
  damage, while the ready-made hero's template items keep working as today (← D17).
- AC6: The character route with no body still creates the ready-made hero exactly as today (← D11); with a
  body it creates the described character and moves the run to ready.
- AC7: The generated API client is regenerated and committed; both lint suites pass.

## Decisions
← D1, D5, D9, D11, D17

## Assumptions
- The full sheet type and the widened character state live in the playthrough module, so the character
  module depends on playthrough and never the reverse.
- Sheet-born items have no template; the attack lookup reads an item's own state when it has none, and
  otherwise behaves as today.
- Armour class is the chosen armour's base plus dexterity as the SRD allows, plus two for a shield, else
  ten plus the dexterity modifier.
- Weapon to-hit is proficiency bonus plus the weapon's ability modifier (finesse takes the better of
  strength and dexterity); damage is the SRD die plus that modifier.

## Out of scope
No agent, no chat, no frontend, no editing after saving, no item mechanics beyond carrying and attacking.
