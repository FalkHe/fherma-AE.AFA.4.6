---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: –
---
# Review: Sprint 08 — "Start adventure" opens a new adventure straight into play, where the Dungeon Master writes the opening scene

## What changed
"Start adventure" on the run screen is live. Pressing it enters the adventure and opens the play screen:
the header names the scene, the transcript reads "Nothing written down yet. The Dungeon Master is opening
the book." under the thinking line for a few seconds, and then the opening scene arrives, written by the
Dungeon Master, with no player row before it. The composer opens after it. Entering happens once: coming
back to the run screen the row reads "In progress" with "Continue", and a reload in the middle of the
opening never starts it a second time. Nothing on the way asks for a character; the ready-made hero is enough.

## How to check it
- On a run whose adventure has not been played, press "Start adventure": the play screen opens with the
  scene name, the empty line and the thinking line (AC1).
- Wait: the opening narration appears whole, no player row above it, and "What do you do?" is back (AC2).
- Go back to the run screen: the row reads "Continue", never "Start adventure" again (AC3).
- Reload during the opening: what was recorded shows and the opening does not run twice (AC4).
- At no point is a character asked for (AC5).

## Heads-up
A seat with no hero at all still reads "Waiting on party" and cannot start; taking the ready-made hero
stays with the character-creation chat. An opening turn that breaks is picked up by the retry of the
long-wait sprint. A network failure while entering keeps you on the run screen with a line to retry.

Brief: docs/intents/010-dm-agent-in-gui/sprints/08-start-adventure-opening-turn/brief.md

## Verdict
