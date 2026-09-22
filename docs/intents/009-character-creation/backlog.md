---
author: fhit:architect
owner: human
created: 2026-09-22
updated: 2026-09-22
stage: approved
---
# Backlog

Dependency-ordered. 01 to 05 are checked in the terminal or on the interactive API page, 06 and 07 in
the browser. 06 and 07 also need the run screen of intent 007, sprint 05, which is still open.

| # | Task | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | The game knows the nine races, twelve classes, skills and alignments a player may pick, and the numbers each of them fixes | – | #45 | done |
| 02 | A character built from those facts gets correct ability scores, hit points, armour class and usable gear, and can be saved to a run in place of the ready-made hero | 01 | #46 | done |
| 03 | In the terminal the Tavern Keeper greets the player, offers the campaign's ready-made hero or turns free words into a race and class, and saves the confirmed character | 02 | #47 | done |
| 04 | The Tavern Keeper covers the whole sheet: ability scores by suggestion, dice or by hand, the story retold in the campaign's voice, two skills, an alignment and the class's equipment choices | 03 | #48 | done |
| 05 | The same conversation can be held over the network, one message at a time, returning the reply and the sheet so far | 03 | #49 | open |
| 06 | Character creation opens as its own page where the player talks to the Tavern Keeper and watches the sheet fill beside the transcript | 05, 007/05 | #50 | open |
| 07 | The player reviews the finished character, saves it, and finds it as a card on the run screen with the party ready | 06, 007/05 | #51 | open |

## Notes

- 04 and 05 can run side by side once 03 is merged.
- Coverage: D1→01,02,03 · D2→03 · D3→03,05 · D4→01,03 · D5→02,04 · D6→04 · D7→01,04 · D8→01,04 ·
  D9→03,07 · D10→04 · D11→03 · D12→03,06 · D13→01,04 · D14→06,07 · D15→03,06 · D16→03,06,07 · D17→02 · D18→01,04.
- Black-box acceptance tests are written for 05 only, the contract the web page rests on; every other
  sprint is covered by the implementer's own tests, one per criterion.
- Not sprints: changing a character after saving (← D9) · levels beyond the first · a list of ready-made
  backgrounds (← D6) · word-by-word streaming of the agent's reply (← D3) · resuming an abandoned conversation (← D12) · several characters per run.

## Proposals

- none yet
