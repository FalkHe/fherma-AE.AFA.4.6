---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/67
---
# Review: Sprint 06 — The play screen shows everything that was recorded

## What changed
Play now has its own screen. An adventure under way reads "In progress" on the run screen, and "Continue"
opens it: a header naming the campaign, the adventure and the scene, and below it the whole transcript
recorded so far, in the wording and layout that was decided. It opens at the newest entry and offers "Jump
to the latest" once you scroll up. Going back returns to the lobby. Reading only: the composer, the buttons
and live updating are the next sprints.

## How to check it
- A run whose adventure is under way reads "In progress" with "Continue", which opens the screen (AC1),
  showing the campaign back link, the adventure title and the scene line (AC2).
- Narration, player rows, system lines, dice, questions and a scene change draw as decided, the system
  lines worded by the screen from recorded values (AC3); a run with nothing written shows its own line (AC4).
- A long transcript opens at the newest entry; scrolling up offers "Jump to the latest" (AC5).
- The layout holds on a narrow screen (AC6); the dark look and translated strings apply throughout (AC7).

## Heads-up
Three things are proposed as their own work rather than done here: the dice chip shows the roll but not
whether it made it and the check line no difficulty, because the game records neither where a player can
read them; a way being opened names the hero and the action but not what opened; and only the first five
hundred entries are read, so a very long adventure would lose its newest. A question draws as an ordinary
Dungeon Master row until the next sprint gives it buttons, and "Start adventure" stays disabled until the
one after.

Brief: docs/intents/010-dm-agent-in-gui/sprints/06-play-screen-transcript/brief.md

## Verdict
Round 1: changes requested — a long transcript opened at its oldest entry instead of its newest and "Jump to the latest" never appeared; small lines printed empty brackets when a roll named no skill, and on a phone they were cut off mid-sentence.
