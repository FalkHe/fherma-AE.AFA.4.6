---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/34
---
# Review: Sprint 08a — a fixture is interacted with, and a creature acts once a turn

## What changed

The things standing in a scene can now be dealt with, in the ways their author wrote. A thorn screen carries the
actions that work on it, each with a difficulty and sometimes things that get past it outright. An interaction
passes on a roll meeting the difficulty, or with no roll if the actor carries one of those things. It changes
nothing in the world — what happens on success is the author's prose for the DM to narrate. And a creature now
gets one action per turn.

## How to check it

- Cutting through the thorn screen with a good roll succeeds; so does carrying what gets past it.
- An unwritten action, a check needing a roll when none was given, and a roll made for something else are each
  refused, recorded for the DM only, with nothing changed.
- A creature that has already acted this turn is refused; in a new turn it can act again.
- A refused attempt costs nothing. Dropping, exits and rolling dice are free.

## Heads-up

- I split sprint 08 as before: this half is interacting and the action rule. Taking, dropping and giving,
  looting a container and using an item are 08b, which needs this first.
- You corrected the brief mid-sprint: dropping is free, following the SRD, where the brief had counted it as
  spending the turn. The action rule shipped here reflects your version.
- Your other ruling — a container in the scene can be looted, so the stolen fleeces come out of the wool sack —
  lands in 08b, where taking lives.

Brief: docs/intents/005-game-state-services/sprints/08a-interact-and-one-action/brief.md

## Verdict

Round 1: approve — the things standing in a scene can now be dealt with in the ways their author wrote them: a
good enough roll gets through, and so does carrying the right tool with no roll at all, while an action the
author never wrote, a check missing the roll it needs, and a roll made for something else are each refused and
noted for the DM, with nothing in the world changed either way. A creature gets one action a turn, read back
from the transcript rather than counted anywhere, and a refused attempt costs it nothing — dropping stays free,
as you ruled, and a test holds that in place.
