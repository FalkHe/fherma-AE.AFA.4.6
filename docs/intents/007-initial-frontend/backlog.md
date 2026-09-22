---
author: fhit:architect
owner: human
created: 2026-09-22
updated: 2026-09-22
stage: approved
---
# Backlog

Dependency-ordered. 01 and 02 have no screen and are checked through the interactive API page; 03 to 09 in the browser.

| # | Task | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | The product can list the campaigns a player may choose from, with title, teaser and number of adventures | – | #37 | done |
| 02 | A player's runs can be read with everything the screens show: campaign, progress, who is at the table, which adventures lie ahead | – | #38 | running |
| 03 | The whole product wears the delivered dark "Goblin Pub" look and is named The Goblin's Tavern | – | – | open |
| 04 | Every page sits behind sign-in under one shared header with an account menu; a signed-out visitor is sent to sign-in and then back to the page they asked for | 03 | – | open |
| 05 | Opening a run shows the campaign, who is at the table and whether their character is ready, plus an invite slot | 02, 04 | – | open |
| 06 | The run screen lists the adventures in order, marks which is next and says what the party is waiting for | 05 | – | open |
| 07 | Signing in lands on a dashboard of the player's runs, or on an invitation to start the first one | 05 | – | open |
| 08 | The dashboard sorts runs under "In progress", "New" and "Archived" and opens on the one that matters | 07 | – | open |
| 09 | "New campaign" lets a player pick a story and drops them straight at its table | 01, 07 | – | open |

## Notes

- 01, 02, 03 start together; 06 and 07 run side by side.
- Not sprints: wiring Start (← D1) · real character creation, invite, sharing, unarchive, rename (← D2–D4, D13) ·
  the play screen · cover art · adopting the design bundle's compiled components (flagged in 03 for veto).
- Coverage: D1 → 01, 02, 06 · D2 → 07 · D3 → 08 · D4 → 05 · D5 → 04 · D6 → 09 · D7 → 02, 07 · D8 → 07 · D9 → 06 ·
  D10 → 09 · D11 → 01–07, 09 · D12 → 07, 08 · D13 → 05 · D14 → 03, 04.
- Users have a username only, no e-mail: the design's e-mail line (account menu, player card) is omitted and the
  username is the name (04, 05). Assumption, open to veto.

## Proposals

- The backend has since gained the "enter adventure" write that Start would call. D1 keeps Start disabled here;
  wiring it would be one small extra sprint after 06 — your call.
