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
- On a fresh run say "a sneaky halfling burglar": the Keeper proposes Halfling Rogue and waits for your yes; answer the name, looks and story questions; the full sheet with hit points, armour class and abilities is printed before the Keeper asks "Save as they stand?"; say yes and the run holds that character.
- Say "take Rosalind": her sheet is printed before the same save question.
- Ask for two things in one sentence ("suggest the scores and show me the sheet"): both happen, nothing crashes.
- Type `quit` at any point before saving: nothing is kept, the run still has no character.

## Heads-up
- Alignment is not asked yet, so the sheet reads Neutral until the next sprint adds the question; skills, dice and by-hand point buy also come with sprint 04.
- The conversation is not stored anywhere: leaving means starting over, by decision.
- A real model needs the OpenRouter key in `.env`; the tests drive the Keeper with a scripted model.

Brief: docs/intents/009-character-creation/sprints/03-tavern-keeper-terminal-chat/brief.md

## Verdict
Round 1: changes requested — asking the Tavern Keeper for two things in one sentence ends the conversation with a technical error and loses everything said so far; before saving, the player never actually sees the sheet, the Keeper only describes the character in words; taking the ready-made hero saves after a bare "Confirm?" without showing who is being taken.
Round 2: approve — creation in the terminal works end to end: the Keeper offers the ready-made hero by name or turns free words into a race and class, prints the finished sheet with hit points, armour class and abilities before asking to save, and only then writes the character; quitting keeps nothing and asking for two things at once no longer breaks the conversation. Blemish for later: the ready-made hero's gear is listed by internal item ids.
