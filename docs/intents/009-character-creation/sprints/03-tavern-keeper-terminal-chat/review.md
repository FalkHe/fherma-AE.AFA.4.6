---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/57
---
# Review: Sprint 03 — the Tavern Keeper in the terminal

## What changed
A player can now create their character in a terminal conversation with the Tavern Keeper. The Keeper greets in the campaign's tone, offers the ready-made hero by name or turns free words such as "a sneaky halfling burglar" into a race and class from the SRD lists, asks for a yes before writing anything down, collects name, looks and story, proposes an ability set, shows the full sheet and saves only after the player confirms. Quitting before that keeps nothing.

## How to check it
- With a run id and your user id, start `app character create --run <id> --user <id>` in the backend container: the greeting names Rosalind Thorn as one way in and building your own as the other.
- Say "take Rosalind": the Keeper confirms, the run holds Rosalind and the command ends with the finality line.
- On a fresh run say "a sneaky halfling burglar": the Keeper proposes Halfling Rogue and waits for your yes; answer the name, looks and story questions; the full sheet appears; say yes to "Save as they stand?" and the run holds that character.
- Type `quit` at any point before saving: nothing is kept, the run still has no character.

## Heads-up
- Alignment is not asked yet, so the sheet reads Neutral until the next sprint adds the question; skills, dice and by-hand point buy also come with sprint 04.
- The conversation is not stored anywhere: leaving means starting over, by decision.
- A real model needs the OpenRouter key in `.env`; the tests drive the Keeper with a scripted model.

Brief: docs/intents/009-character-creation/sprints/03-tavern-keeper-terminal-chat/brief.md

## Verdict
