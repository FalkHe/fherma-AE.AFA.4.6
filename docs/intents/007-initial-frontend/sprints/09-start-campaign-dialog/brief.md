---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 09: start a campaign dialog

## Task
Wire the dashboard's new-campaign button to the select dialog from the design — title, the shortened intro line, and
one card per catalogue campaign with cover-art placeholder, title, teaser and adventure count. Choosing one creates the
run, shows the "Rolling up …" state and opens that run's screen; starting the same campaign again is allowed with no
warning.

## Outcome
From the dashboard, "Create new campaign" opens the campaign choices, picking one lands on a brand-new run's screen,
and doing it twice leaves two runs on the dashboard.

## Acceptance criteria
- AC1: The dialog "Select a campaign" lists every campaign from the catalogue with placeholder art, title, teaser and
  adventure count, and no tone badge (← D11).
- AC2: Choosing a campaign creates the run and opens its run screen; the creating state reads "Rolling up "<title>" —
  taking you to the table." (← D10, D11).
- AC3: Choosing a campaign the player already has a run of neither warns nor blocks, and the dashboard afterwards
  shows both runs (← D6).
- AC4: A failed creation leaves the dialog open with a retryable error and creates nothing.
- AC5: Dismissing the dialog creates nothing and returns to the dashboard.
- AC6: The intro line reads "Choose the story your party will play." — no rename is promised (← D11).

## Decisions
← D6, D10, D11

## Assumptions
- The dialog is a modal over the dashboard, not its own address.
- The run list is refreshed after creation so returning shows the new run.
- The write carries the same protection every other write in this app carries.

## Out of scope
No rename or delete · no search, filter or sort of campaigns · no cover art.
