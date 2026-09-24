---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/79
---
# Review: Sprint 08 — The new game flow goes live

## What changed
Every turn now runs through the new game flow. What the player types is read into a small set of checked decisions, the referee rule picks each next step, and the rules layer does every roll and every change. Talking, searching, moving between scenes, forcing fixtures and fighting all work on the live site with the same message box, the same roll and answer buttons, the same dice chip and the same transcript lines as before. A search over an authored clue asks for the authored roll with its ability, skill and difficulty; a move records the scene change; an attack binds its target, asks the player for the heroes' initiative roll, rolls for the enemies automatically, and every hit is followed by its damage. A hero brought to zero hit points ends the run in defeat with one closing narration about the ending, never as a fighter still standing. A pending roll survives a server restart and resumes the same turn. The terminal game uses the same path.

## How to check it
- Open a run in the browser and talk to Mira: the reply arrives as before and the box reopens.
- Go north and search the wool-marked cut: a Perception roll button with its difficulty appears; press it and read the discovery.
- Climb to the lair and attack a goblin: initiative is asked once, then the fight runs hit by hit until someone falls.

## Heads-up
The old flow's files remain on disk until sprint 09 removes them. The narrator has one voice; a selectable tone is still a proposal.

Brief: docs/intents/011-game-flow/sprints/08-new-flow-live/brief.md

## Verdict
