---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 06: run adventures list

## Task
Add the adventures section to the run screen: one numbered row per adventure with title, a teaser from its intro and a
status badge, following the run overview. The first unplayed adventure reads "Next up" when every character is ready
and "Waiting on party" with the reason otherwise, and carries the "Start adventure" button, which is present but
disabled in this intent; later adventures read "Locked", finished ones "Done".

## Outcome
In a run whose character does not exist yet, adventure one reads "Waiting on party" with a hint and a disabled
"Start adventure", the rest read "Locked", and nothing on the screen can start an adventure.

## Acceptance criteria
- AC1: Adventures render in campaign order with numeral, title, teaser and badge (← D9, D11).
- AC2: The first unplayed one reads "Next up" when all characters are ready, "Waiting on party" plus the reason
  otherwise (← D9).
- AC3: Adventures after it read "Locked"; completed ones read "Done" (← D9).
- AC4: "Start adventure" is rendered, disabled in every state, and calls nothing (← D1).
- AC5: Every status shown comes from the overview read — none is invented in the browser — and all copy goes through
  translation keys.

## Decisions
← D1, D9, D11

## Assumptions
- The disabled button carries a short explanation on hover and focus.
- Badge wording is the frontend's mapping of the API's plain statuses.

## Out of scope
No adventure entry or play screen · no per-adventure detail page · no scene or map content.
