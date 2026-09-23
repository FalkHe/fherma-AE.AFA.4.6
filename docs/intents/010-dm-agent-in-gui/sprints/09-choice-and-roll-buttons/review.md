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
mid-way still keeps the thinking line until the long-wait sprint. Until this sprint the Dungeon Master rolled every check itself and never handed the dice to the hero. Two faults in the dice tools were behind it: the game gave the model no field names for a roll's context, so it left it empty and the tool failed with an error the model then relayed as prose, and a player roll that did get asked for was written twice when the turn resumed. Both are fixed here, a goblin's weapon is now found regardless of spelling, and the Dungeon Master's instructions say a hero's checks and saves go to the player while monsters, hidden rolls and damage stay with the game. Monsters could not roll either: the Dungeon Master saw several identical goblins and an innkeeper as bare names, aimed the attack at the wrong one, got a bare refusal and made the exchange up. Creatures are now listed by id with their role and weapons, the attack tools accept a name and answer a miss with the list of who is present, and a player roll can no longer be a dice-less number or a monster's roll. Two goblins striking in one turn used to corrupt the game's bookkeeping and leave a goblin's roll on the player's screen as a stuck button; tool calls now run one at a time, a monster's roll is never counted as the player's, and the Dungeon Master writes each narration against a summary of what the dice and tools actually decided this turn, so a hit is not told as a miss and a fallen hero is told as fallen. An attack must name its target and is refused when the name does not match the creature. Expect turns to stop on a roll now.

Brief: docs/intents/010-dm-agent-in-gui/sprints/09-choice-and-roll-buttons/brief.md

## Verdict
Round 1: approve — when the Dungeon Master puts a question, its answers stand as buttons and nothing else can be sent until one is picked; the pick appears as the player's own words and the turn carries on; a called check shows its difficulty with a single roll button whose press produces the dice result with its made-it or missed mark, all of it still waiting after closing and reopening the screen. Noted for follow-up: in live play the Dungeon Master still rolls checks itself instead of handing the dice over, so the roll button almost never comes up on its own.
Round 2: changes requested — an attempt to make the Dungeon Master hand the dice to the hero made it ask the player which ability and difficulty to use instead of rolling, and the roll button still never appeared on its own; that change was reverted, so the branch is the state approved in round 1, and the dice hand-over is proposed as its own sprint.
Round 3: changes requested — a hero's own check now stops the turn with a single roll button whose press produces the result and carries the scene on, still waiting after a reload; the Dungeon Master's own rolls do not work yet: in a fight it said it could not work out the monster's attack and made the exchange up in prose, once offered a "roll" with no dice in it that blocked the message box, and asked plainly to let the goblin strike it turned the monster's attack into another roll for the hero.
Round 4: changes requested — the Dungeon Master now rolls a monster's attack itself and a goblin's blow lands on the hero with her hit points falling on screen, but every turn in which two goblins struck left the play screen holding a roll button that belongs to a goblin: the message box stays closed and pressing it produces no dice; the written account also drifts from what the dice decided, a goblin's hit narrated as a miss and the hero at no hit points described as standing ready; and an attack on "the nearest goblin raider" wounded the innkeeper, because the Dungeon Master narrates the walk north without moving the party.
Round 5: changes requested — the dice now work on both sides in live play: a called check waits for your press and still waits after a reload, a goblin's blow is rolled, resolved and shown with the hit points falling, two goblins striking in the same turn no longer leave a dead roll button, and an attack aimed at a goblin never lands on the innkeeper; what still fails is the written account: with the hero at no hit points the Dungeon Master calls her bruised but standing and asks what she does next, and one goblin blow recorded as a hit was told as a wound while no hit points came off.
