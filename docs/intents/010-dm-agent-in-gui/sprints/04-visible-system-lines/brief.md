---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 04: The transcript shows what the Dungeon Master did

## Task
Give the mechanics that change the world — taking, giving, dropping, damage and healing, opening a way, entering a scene — and the rule lookup a player-visible record carrying who and what changed as plain values, and leave refusals and the Dungeon Master's private mechanics hidden as they are. No wording is produced by the game: the screen puts words to the values.

## Outcome
A terminal turn in which the hero looks up a rule and picks something up leaves two visible lines in the transcript read, one naming the rule's topic and one naming the hero and the item.

## Acceptance criteria
- AC1: Given a turn that looks up a rule, when the transcript is read as a player, then a visible entry names the topic and never the rules text.
- AC2: Given a turn that moves an item, changes hit points or opens a way, when the transcript is read, then a visible entry carries who, what and the numbers before and after.
- AC3: Given a mechanic the Dungeon Master used privately or a refused action, when the transcript is read as a player, then no visible entry is added.
- AC4: The model cannot write a visible line itself; only the server's own mechanics do.

## Decisions
← D10

## Assumptions
- The list of mechanics that leave a line is the server's, fixed in code.
- The transcript read gains these entries as a new visible kind; older transcripts simply lack them.

## Out of scope
The wording and rendering of the lines (06) · conditions on the party card (← D7).
