---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/69
---
# Review: Sprint 07 — The player writes what they do, watches the Dungeon Master think as dice and questions appear, then reads the narration

## What changed
The play screen can now be played. Below the transcript sits a composer asking "What do you do?". Sending
words shows them at once under the hero's name, the composer closes with "The Dungeon Master has the floor."
and a thinking line appears at the foot of the transcript. While the turn runs, everything the game records
— a rule looked up, dice, a question — appears within a couple of seconds, above the thinking line. When
the narration lands the thinking line goes and the composer asks again. The screen listens to the run's
notice stream and re-reads the transcript on every notice; the browser reopens the stream on its own when
the server closes it. While a turn runs the screen also re-reads every few seconds on its own, so a lost
notice cannot leave it stuck.

## How to check it
- Open an adventure in progress, write an action and send it: your row appears immediately and the
  composer reads "The Dungeon Master has the floor." (AC1).
- While the Dungeon Master thinks, dice and short system lines show up one by one above the thinking
  line, before the narration (AC2).
- When the narration arrives it appears whole, the thinking line disappears and "What do you do?" is back
  (AC3).
- Reload the page in the middle of a turn: everything recorded so far is there, and the thinking line
  stays only until the turn finishes (AC4).
- Leave the screen open for more than five minutes: new entries still arrive (AC5).

## Heads-up
When the Dungeon Master asks a question or calls for a roll, the composer stays closed with its own
line ("The Dungeon Master is waiting on one of those." / "The dice go first.") but offers no buttons yet — those are the
sprint after next. A turn that breaks mid-way keeps the thinking line until the long-wait sprint adds its
give-up wording. Entries lag about two seconds behind the game and nothing streams word by word. Round 1
found the notice stream dying on the server the moment it opened (a fault older than this sprint); it is
fixed here.

Brief: docs/intents/010-dm-agent-in-gui/sprints/07-taking-a-turn/brief.md

## Verdict
Round 1: changes requested — nothing shows up while a turn is running: dice and rule lookups only appear at the very end together with the narration, because the live connection the screen opens dies a couple of seconds later and is never re-established; a player who reloads mid-turn is left staring at "The Dungeon Master is thinking…" with the composer closed, even long after the narration was recorded.
Round 2: approve — writing an action shows it under the hero's name at once, the composer steps aside while the Dungeon Master has the floor, dice and rule lookups appear above the thinking line within a couple of seconds, and the finished narration arrives whole with the composer open again; reloading mid-turn keeps everything recorded and shows the thinking line only until that turn ends, and the live connection reopens itself after the server drops it five minutes in.
