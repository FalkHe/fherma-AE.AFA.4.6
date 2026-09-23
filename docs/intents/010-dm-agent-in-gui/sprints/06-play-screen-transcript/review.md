---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: –
---
# Review: Sprint 06 — The play screen shows everything that was recorded

## What changed
Play now has its own screen. An adventure under way reads "In progress" on the run screen, and "Continue"
opens it: a header naming the campaign, the adventure and the scene, and below it the whole transcript
recorded so far — the Dungeon Master's narration, the player's words, the small system lines, the dice and
the scene dividers, in the wording and layout that was decided. It opens at the newest entry and offers
"Jump to the latest" once you scroll up. Going back returns to the lobby with nothing lost. Reading only:
the composer, the buttons and live updating are the next sprints.

## How to check it
- Open a run whose adventure is under way: its row reads "In progress" with "Continue", which opens the
  play screen (AC1).
- The header shows the campaign back link, the adventure title and the scene line (AC2).
- A transcript with narration, player rows, system lines, dice, questions and a scene change draws each as
  decided, the system lines worded by the screen from recorded values (AC3).
- A run nothing has been written in yet shows its own line instead (AC4).
- A long transcript opens at the newest entry; scrolling up offers "Jump to the latest" (AC5).
- On a narrow screen the layout holds (AC6), and the dark look and translated strings apply throughout (AC7).

## Heads-up
The dice chip shows the roll but not whether it made it, and the check line carries no difficulty: the game
records neither anywhere a player can read, so the screen cannot show them. Recording them is proposed as
its own piece of work. A transcript longer than five hundred entries is trimmed at the oldest for now. A
question is drawn as an ordinary Dungeon Master row until the next sprint gives it buttons, and "Start
adventure" stays disabled until the one after that.

Brief: docs/intents/010-dm-agent-in-gui/sprints/06-play-screen-transcript/brief.md

## Verdict
