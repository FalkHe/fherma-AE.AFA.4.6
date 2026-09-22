---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/58
---
# Review: Sprint 04 — the whole conversation

## What changed
The Tavern Keeper now takes a player through the complete sheet. Ability scores can be set three ways: a suggested set for the class, dice rolled by the game, or spending the 27 points by hand with the points left shown after every change. Name, looks and story are read back in the campaign's tone and corrected as often as the player likes. Two skill proficiencies and an alignment are proposed from the story with a reason each, the class's own skills fill in automatically, and the class's either-or equipment choices are walked one at a time with a plain hint and a "just the default" shortcut. The review before saving shows alignment, skills and equipment, and the ready-made hero's gear is now listed by name.

## How to check it
- Start `app character create --run <id> --user <id>`, pick a race and class, then say "I'll spend the points myself" and give six scores: the Keeper answers with the points left; give a score above 15 and it names the problem.
- Say "roll for me": a rolled set appears; say it again and it re-rolls.
- Tell name, looks and story: the Keeper reads them back in the tavern's voice and asks if that fits; correct the name and the sheet shows the corrected one.
- The Keeper proposes two skills and an alignment with reasons; name others and they replace the proposal.
- For the equipment choices, pick one option and then say "just the default": the sheet shows your pick and the defaults elsewhere.

## Heads-up
- Rolled scores bypass point buy only in the terminal conversation; the web route still validates point buy, to be settled with the network sprint.
- "Any simple weapon" or "any martial weapon" options still resolve to a mace or a longsword; the Keeper says the tavern picks a fitting one.

Brief: docs/intents/009-character-creation/sprints/04-full-creation-conversation/brief.md

## Verdict
