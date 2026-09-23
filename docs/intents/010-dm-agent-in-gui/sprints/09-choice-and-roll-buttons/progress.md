---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
stage: done
---
# Progress: Sprint 09

| WI | Status | Note |
|---|---|---|
| 1 | done | DM names ability, skill, DC when calling for a roll |
| 2 | done | pending derived from the read; verdict; DC strings |
| 3 | done | answer and roll buttons; verdict mark on the chip |
| 4 | done | prompt slot before the thinking line; verdict to the chip |
| 5 | done | buttons wired: answer sends, roll rolls, composer precedence |

Status: `open | running | done | failed`

## Issues
After round 2 the human asked for the dice to be fixed properly for both the Dungeon Master's rolls and player rolls; done as round 3 on the same branch: typed roll context for the tools, idempotent player-roll request on resume, case-insensitive attack lookup, prompt routing a hero's checks to the player.
Same mode as 07 and 08: minimal component tests, no qa agent, functionality over polish.
Accepted the architect's assumptions: a question that arrives with no options leaves the composer open, since the turn route accepts free text in exactly that case; a check whose difficulty the Dungeon Master did not name shows no "DC n" and no mark, never an invented one.
Local main carried an unpushed backlog commit that reached origin through the sprint 08 merge; reset local main to origin before branching.

## Backlog proposals
(withdrawn) The dice hand-over turned out to be two tool faults, fixed in round 3 of this sprint.

## Verify
Round 1: approve, no failed criteria. Finding beside the criteria: the Dungeon Master's prompt never tells it when to hand the dice to the player, so every check so far was self-rolled and the roll button is unreachable in live play; fixed in the same sprint as a prompt change, then verified once more.
Round 2: changes-requested — AC3, AC4, AC5 unreachable in live play because the Dungeon Master still never asks for a roll, and the prompt change made turns stall on clarification questions. Reverted the prompt change; the branch is the round-1 approved state; merge request left as draft per process, last verdict standing.
Round 3: changes-requested — player rolls (checks 1, 2, 4) pass live; the Dungeon Master's own rolls fail: the model aimed the goblin's attack at the innkeeper (an object with no attacks), the attack tool refused, damage refused in turn, and the model fabricated a constant "roll 10" request and narrated the attack itself.
Round 4: changes-requested — player rolls and a single goblin's attack pass live; a second goblin's roll request is left unanswered (SQLAlchemy "Session.add() within flush" warning at the same moment) and the server counts it as awaiting the player, so the screen shows a stuck monster roll button; the model narrates hits as misses and a downed hero as standing; three attack rolls were made with the plain dice tool so the model judged the miss itself; an attack meant for a goblin hit the innkeeper since the party had not actually moved.
