---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/27
---
# Review: Sprint 04 — the run gets its character and becomes playable

## What changed

A game now gets its player character, and with that it is ready to play. The character is made rather than
taken from the adventure's cast: it belongs to the player, carries the starting pack as real items it could
later drop or give away, and starts at full health. Games can also be renamed and put away.

## How to check it

- Creating the character answers it — name, health, armour — and the game turns from *set up* to *ready*;
  a second attempt is refused.
- The character carries the five items of its pack, each a thing in the world rather than prose, none of it
  lying in a scene. A game can be renamed.
- A ready, in-progress or finished game can be archived: it still lists and reads, but renaming it or giving
  it a character is refused.
- Archiving a game that was never started removes it altogether — gone from the list, and not found.

## Heads-up

- The two rules you set mid-sprint are what shipped: no unarchive, so an archived game is kept to re-read its
  story and never played on; a finished game can be archived; a never-started one is deleted. The brief still
  says archiving flips back and forth — now wrong — and no decision line covers this.
- Renaming needed a request method the browser was not allowed to use; it is allowed now.
- The step that moves a ready game to in-progress exists, but nothing reaches it — that belongs to the turn.

Brief: docs/intents/005-game-state-services/sprints/04-character-and-shelf-life/brief.md

## Verdict
