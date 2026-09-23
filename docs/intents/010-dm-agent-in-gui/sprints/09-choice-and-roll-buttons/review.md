---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/71
---
# Review: Sprint 09 — When the Dungeon Master asks or calls for a roll, only the offered buttons work; the game rolls

## What changed
When a turn stops on a question, its answers stand as buttons beneath it and the composer closes with
"The Dungeon Master is waiting on one of those." Picking one writes it as your own row and the thinking
line returns while the turn continues. When a turn stops on a check, the line reads "{ability} ({skill})
· DC {n}" with one "Roll {notation}" button and the composer reads "The dice go first." Pressing it makes
the game roll: the button gives way to the dice chip with breakdown, total and a made-it or missed mark,
and the turn continues. Closing the browser and coming back finds the same buttons waiting, because what
is waiting is read from the transcript itself. The Dungeon Master is now told to name ability, skill and
difficulty whenever it calls for a roll, which is where the difficulty and the mark come from.

## How to check it
- A turn stopped on a question shows its answers as buttons and the closed composer; nothing else sends (AC1).
- Pick an answer: it appears as your row, the thinking line comes back until the turn ends (AC2).
- A turn stopped on a check shows the check line with its difficulty and one roll button (AC3).
- Press it: the dice chip appears with breakdown, total and mark, and the turn goes on (AC4).
- Close the tab while a question or roll waits and reopen the screen: the same buttons wait (AC5).

## Heads-up
A check whose difficulty the Dungeon Master did not name shows no "DC n" and no mark, never an invented
one; older transcripts recorded before this sprint look that way. A question that arrives with no answers
leaves the composer open, since the game accepts free text in exactly that case. A turn that breaks
mid-way still keeps the thinking line until the long-wait sprint. The first verification found that the
Dungeon Master had never once handed the dice to a player, rolling every check itself; its instructions
now say that a hero's checks and saves go to the player as a roll button while monsters, hidden rolls and
damage stay with the game. Expect more turns to stop on a roll than before.

Brief: docs/intents/010-dm-agent-in-gui/sprints/09-choice-and-roll-buttons/brief.md

## Verdict
Round 1: approve — when the Dungeon Master puts a question, its answers stand as buttons and nothing else can be sent until one is picked; the pick appears as the player's own words and the turn carries on; a called check shows its difficulty with a single roll button whose press produces the dice result with its made-it or missed mark, all of it still waiting after closing and reopening the screen. Noted for follow-up: in live play the Dungeon Master still rolls checks itself instead of handing the dice over, so the roll button almost never comes up on its own.
