---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/75
---
# Review: Sprint 04 — One trustworthy picture of the moment, and long memory

## What changed
The game can now assemble, in one read, everything the Dungeon Master needs to judge a moment: the run, adventure and scene, every creature present with its role, health, whether it is down, its attitude and attacks, what everyone carries, the fixtures and what has already been done to them, the exits and their conditions, the authored facts and consequences, the hidden clues with their difficulties, and the last twenty visible transcript entries. The same picture comes in a public form for narration that leaves out every hidden clue, difficulty and private intent. Roles are worked out from party membership, attitude and weapons, not stored. If a scene or hero cannot be found, the read fails outright rather than handing back half a picture. Recalling older play now returns whole turns: the matching narration together with the player's words and rolls from that turn. Nothing in the running game changes yet; these reads are for the new flow.

## How to check it
- In the merge request, the projection test loads the goblin lair and finds goblins with attacks, a fixture with an achieved outcome, an exit with a condition and a hidden clue.
- The public-view test walks the whole picture and finds no difficulty, ability, skill or hidden fact.
- The recall test asks about something older than the recent window and gets back that turn's player action and narration together.

Brief: docs/intents/011-game-flow/sprints/04-situation-and-memory/brief.md

## Verdict
Round 1: changes requested — reading the goblin lair returns all three goblins as the hero's allies, because a creature only counts as an enemy once an explicit hostility switch is set and nothing in the adventure ever sets it.
Round 2: approve — walking into the goblin lair reads all three goblins as enemies without anyone flagging them while the unarmed innkeeper stays a bystander; one read gives the whole truth of a moment, the storytelling version keeps every clue, difficulty and private motive out of sight, recalling something older returns the whole turn, and a broken scene fails outright.
