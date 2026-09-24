---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/76
---
# Review: Sprint 05 — Every game action as one validated operation, remembered across restarts

## What changed
The new game flow now has its memory and its hands. Its memory is the small set of facts kept for the turn in progress: whose turn it is, the action under way and the roll it owns, the fight order, the question or roll the player still owes, an unresolved wound, queued reactions and the narration drafted so far. It survives a server restart unchanged; at turn end everything but the fight order is cleared, and the fight order goes when the fight ends. Its hands are twenty-three named operations, each doing one thing: ask for a roll or a question, record the answer, make a check or save, settle initiative, use a fixture, exit or item, resolve an attack, apply damage, record narration, close the turn, finish the run. Each first checks that the creature, item, exit or answer it names is really in the scene; a stale or invented name is refused before anything changes, and a spent roll cannot be applied twice. Roll requests still write the line the dice chip reads. Play is unchanged: the old flow serves turns until sprint 08.

## How to check it
- In the merge request, one test saves and restores a pending roll request and a fight order and gets them back identical, then shows turn close clears everything but the fight order.
- One test walks every operation kind and finds exactly one handler.
- One test names an item that is not in the scene and shows the refusal with no change made.

Brief: docs/intents/011-game-flow/sprints/05-operations-and-turn-memory/brief.md

## Verdict
Round 1: changes requested — closing a turn does not forget an unresolved wound, so a hit never turned into damage carries into the next turn; handing an item from one creature to another is the one action that does not first check both creatures are in the scene.
Round 2: approve — closing a turn now forgets an unresolved wound along with the rest of the turn's memory, handing an item refuses a giver or receiver that is not in the scene before anything happens, and the fight order restores exactly as saved; an interrupted roll request and an active fight survive a restart, every action has one handler, stale names are refused before any change, a spent roll cannot be applied twice, and play is unchanged until the new flow is switched on.
