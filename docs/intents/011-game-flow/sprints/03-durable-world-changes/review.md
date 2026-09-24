---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/74
---
# Review: Sprint 03 — Lasting world changes owned by the rules layer

## What changed
What a hero does to the world now sticks: forcing the thorn screen or cutting the wool sack is remembered on the object, so the way stays open after a reload. Creatures can be marked hostile, leave the scene and remember where they went; the next adventure can be entered; a run can finish as a victory, a defeat or an authored ending, with the outcome in the transcript. Expected setbacks such as an item out of reach or an exit that does not match come back as a plain refusal the Dungeon Master can narrate, not an error. Every transcript line is now written by the rules layer alone; the Dungeon Master's engine saves nothing itself. The always-refusing item use is gone.

## How to check it
- Force open the thorn screen in a run, reload the run: the screen is still open.
- Try to take an item lying in another scene: the Dungeon Master tells you it is out of reach; no error.
- Leave through the final exit of the last adventure: the run is marked finished and the transcript carries the ending.

## Heads-up
Until the new flow replaces the old one, the Dungeon Master may attempt a second action in one turn, because the guard against it read old transcript entries and had to go.

Brief: docs/intents/011-game-flow/sprints/03-durable-world-changes/brief.md

## Verdict
Round 1: approve — forcing a fixture open sticks and survives a reload, a run can finish as victory, defeat or authored ending with the ending in the transcript, expected setbacks come back as a plain refusal the Dungeon Master can narrate, and every transcript line is written by the rules layer alone.
