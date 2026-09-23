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
mid-way still keeps the thinking line until the long-wait sprint. Until this sprint the Dungeon Master rolled every check itself and never handed the dice to the hero. Two faults in the dice tools were behind it: the game gave the model no field names for a roll's context, so it left it empty and the tool failed with an error the model then relayed as prose, and a player roll that did get asked for was written twice when the turn resumed. Both are fixed here, a goblin's weapon is now found regardless of spelling, and the Dungeon Master's instructions say a hero's checks and saves go to the player while monsters, hidden rolls and damage stay with the game. Expect turns to stop on a roll now.

Brief: docs/intents/010-dm-agent-in-gui/sprints/09-choice-and-roll-buttons/brief.md

## Verdict
Round 1: approve — when the Dungeon Master puts a question, its answers stand as buttons and nothing else can be sent until one is picked; the pick appears as the player's own words and the turn carries on; a called check shows its difficulty with a single roll button whose press produces the dice result with its made-it or missed mark, all of it still waiting after closing and reopening the screen. Noted for follow-up: in live play the Dungeon Master still rolls checks itself instead of handing the dice over, so the roll button almost never comes up on its own.
Round 2: changes requested — an attempt to make the Dungeon Master hand the dice to the hero made it ask the player which ability and difficulty to use instead of rolling, and the roll button still never appeared on its own; that change was reverted, so the branch is the state approved in round 1, and the dice hand-over is proposed as its own sprint.
Round 3: changes requested — a hero's own check now stops the turn with a single roll button whose press produces the result and carries the scene on, still waiting after a reload; the Dungeon Master's own rolls do not work yet: in a fight it said it could not work out the monster's attack and made the exchange up in prose, once offered a "roll" with no dice in it that blocked the message box, and asked plainly to let the goblin strike it turned the monster's attack into another roll for the hero.
