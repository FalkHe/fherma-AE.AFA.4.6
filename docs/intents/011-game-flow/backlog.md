---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: approved
---
# Backlog

Steps 01–03 harden the rules layer under the running game; 04–07 build the new flow beside it; 08 switches every turn over; 09 removes the old machinery.

| # | Task | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | Every authored secret and fixture action names its ability and skill as data, so a check never depends on reading prose | – | #68 | done |
| 02 | Fights start with one roll per side, a critical hit really hurts more, and a fallen hero counts as fallen everywhere | 01 | #69 | running |
| 03 | Opening a way, moving, changing attitudes, leaving, finishing a run and recording what happened are lasting changes owned by the rules layer alone | 02 | #70 | open |
| 04 | The game can load one complete, trustworthy picture of the current moment, plus older narrative memory when the player refers back to it | 03 | #71 | open |
| 05 | Every concrete thing the game can do exists once as a validated operation, and a paused roll or a running fight survives a server restart | 04 | #72 | open |
| 06 | The storyteller decides one narrow thing at a time from facts it may see, and prose is written only from what actually happened | 05 | #73 | open |
| 07 | One rule decides what happens next, so a landed hit always reaches damage, every eligible enemy acts once, and a turn never ends with something owed | 06 | #74 | open |
| 08 | Every turn the player takes runs through the new game flow, with rolls, answers, fights and restarts behaving as before or better | 07 | #75 | open |
| 09 | The replaced game machinery and its outdated documentation are gone, leaving one way the game works | 08 | #76 | open |

## Notes

- Testing is held to the intent's minimal lists; each sprint may fold them into one test file.
- Sprint 09 of intent 010 patched the old flow; those backend changes may be overwritten freely. Its approved frontend must keep working: text-only turn body, the three waiting markers, the request event's ability, skill and difficulty, and the same transcript entry types.
- Intent 010 sprints 10–13 are out of scope here; 10 and 13 wait for sprint 08, 11 and 12 could run alongside.

## Proposals

- A derived open/done status per roll request in the events read is optional in both documents and in no sprint; the frontend does not need it today.
- Whether a hero's own requested roll may show its difficulty to the player is assumed yes in sprint 05, matching the shipped dice chip; veto there if the difficulty should stay hidden.
