---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/79
---
# Review: Sprint 08 — The new game flow goes live

## What changed
Every turn now runs through the new game flow. Talking, searching, moving between scenes, forcing fixtures and fighting all work on the live site with the same message box, the same roll and answer buttons, the same dice chip and the same transcript lines as before. A search over an authored clue asks for the authored roll with its ability, skill and difficulty; a move records the scene change; an attack binds its target, asks the player for the heroes' initiative roll, rolls for the enemies automatically, and every hit is followed by its damage. A hero brought to zero hit points ends the run in defeat with one closing narration about the ending, never as a fighter still standing. A pending roll survives a server restart; the terminal game uses the same path.

## How to check it
- Open a run in the browser and talk to Mira: the reply arrives as before and the box reopens.
- Go north and search the wool-marked cut: a Perception roll button with its difficulty appears; press it and read the discovery.
- Climb to the lair and attack a goblin: initiative is asked once, then the fight runs hit by hit until someone falls.

## Heads-up
The old flow's files remain on disk until sprint 09 removes them. The narrator has one voice; a selectable tone is still a proposal.

Brief: docs/intents/011-game-flow/sprints/08-new-flow-live/brief.md

## Verdict
Round 1: changes requested — typing a plain conversational turn into an existing campaign ended in a server error and left that campaign stuck on "The Dungeon Master is thinking…" with the message box closed; a campaign that was waiting on a dice roll from before the change refuses the roll button with an error, so it cannot be continued either.
Round 2: changes requested — the two problems from the last round are fixed, the frozen campaign plays on, and talking and moving work cleanly; but when the Dungeon Master asks for a dice roll, pressing the roll button does nothing and the campaign stays stuck on that request.
