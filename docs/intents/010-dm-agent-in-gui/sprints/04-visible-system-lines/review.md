---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/65
---
# Review: Sprint 04 — The transcript shows what the Dungeon Master did

## What changed
The things that change the world now leave a record a player may see: taking, giving and dropping an item,
damage, opening a way, and entering a scene, each carrying who did it, what it was and the numbers before
and after. Looking a rule up leaves a line naming the topic. Refusals and the Dungeon Master's private
checks leave nothing, as before. The game writes no wording — only values; the screen puts words to them.

## How to check it
- Play a terminal turn in which the hero looks up a rule and picks something up, then read the transcript:
  two visible entries, one naming the rule's topic and never its text, one the hero and the item (AC1, AC2).
- Wound the hero and read again: an entry carries the hit points before and after (AC2).
- Attempt something that is refused, or let the Dungeon Master check something privately: nothing visible
  is added (AC3).
- The model cannot write one of these lines at all — only the game's own mechanics do, held in place by a
  test rather than by convention (AC4).

## Heads-up
Entering an adventure never recorded the scene before; it does now, so a fresh adventure's transcript
begins with a scene entry. Nothing can heal a hero yet, so the hit-point line only ever falls today. Older
transcripts simply lack these entries. A rule heading also reached the Dungeon Master split letter by
letter until now; it arrives readable.

Brief: docs/intents/010-dm-agent-in-gui/sprints/04-visible-system-lines/brief.md

## Verdict
Round 1: changes requested — the written description of every mechanic still said that taking, dropping, giving, wounding and entering a scene leave nothing visible, which would mislead whoever builds the screen on top of this.
Round 2: approve — the transcript now records what the Dungeon Master actually did: a rule looked up by its topic, an item taken, given or dropped, hit points falling, a way opening and a scene entered, each carrying who acted and what changed as plain values, while refused attempts and private checks stay hidden as before.
