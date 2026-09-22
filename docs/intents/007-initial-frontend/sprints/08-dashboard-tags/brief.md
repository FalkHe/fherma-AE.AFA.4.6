---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 08: dashboard tags

## Task
Add the three tags above the run list and filter the list by the selected one, with archived runs visible only under
their own tag — muted, view-only, introduced by a note saying they are kept as they are. The dashboard opens on
"In progress", falls back to "New" when nothing is in progress, and shows the first-campaign invitation when there are
no runs at all.

## Outcome
A player with one new and one archived run lands on "New" showing only that run, and finds the archived one under
"Archived" — muted, buttonless, under a note that archived runs are kept and read-only.

## Acceptance criteria
- AC1: The tags "In progress", "New" and "Archived" render and switching one filters the list (← D3).
- AC2: "New" holds runs not yet started, "In progress" runs whose adventure was entered, "Archived" archived runs (← D3).
- AC3: Archived cards are muted, carry no button, cannot be opened, and the note says archived runs are kept and
  view-only with no mention of unarchiving (← D3).
- AC4: The dashboard opens on "In progress", or on "New" when nothing is in progress; with no runs at all the
  invitation shows and no tags do (← D12).
- AC5: The chosen tag lives only in the screen's own state — nothing is written to the device.

## Decisions
← D3, D12

## Assumptions
- Filtering is client-side over the one list read; no new query parameter.
- Finished runs sit under "Archived" (← D11 agent's call).
- A tag with no runs shows a short "nothing here" line, not the first-campaign invitation.

## Out of scope
No archive or unarchive action · no server-side filtering · no per-tag counts beyond what the design shows.
