---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/26
---
# Review: Sprint 03 — a campaign run starts with its world already in it

## What changed

A player can start a game. Starting one fixes the version of the adventure it will be played on, so later
authoring cannot change a game in progress; it makes the starter its owner; and it brings the declared world
into being at once — every figure, fixture and item the adventures name, including what each carries, none
of it placed yet. A player can also list their games and open one.

## How to check it

- Starting a game answers it: which campaign, that it is only *set up* so far, and when it began.
- Starting Greenhollow brings its thirteen objects into being, none anywhere yet, and writes no transcript entry.
- Starting the same campaign again gives a second, separate game: a finished adventure can be replayed.
- The list shows only your own games, newest first, archived included; somebody else's and a non-existent one
  answer the same "not found", so no one can probe for another player's game. An unknown campaign is refused.

## Heads-up

- The brief contradicted itself: it requires reading one game by id while its scope note forbids a
  "single-run state read". A game's row is not its state and the next sprint assumes the read, so three
  endpoints ship rather than two.
- Nothing is placed yet and there is no character — both by design, both next.

Brief: docs/intents/005-game-state-services/sprints/03-campaign-run-starts-with-world/brief.md

## Verdict

Round 1: approve — a player can start a game, and starting it brings the whole declared world into being with
nothing placed yet; the list and the single read show only the caller's games, and another player's game is
indistinguishable from one that does not exist. Three endpoints rather than the brief's two is the right call:
what ships is the game's row, not its state. Two starts of one campaign give two independent games, so a
finished adventure can be replayed.
