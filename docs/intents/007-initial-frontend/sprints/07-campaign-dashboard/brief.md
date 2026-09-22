---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 07: campaign dashboard

## Task
Replace the landing page with the dashboard from the design: a greeting with a one-line subtitle counting the player's
runs, one card per run with cover-art placeholder, campaign title, status badge, teaser, an "Adventure n of m ·
1 player · Created …" line and a "Begin" or "Resume" button opening the run screen, plus the "Start a new campaign"
card. With no runs, show the invitation to start the first campaign with the same prominent button; a run whose
campaign content is gone shows muted as unavailable and explains itself on click instead of opening.

## Outcome
A player with runs sees one card per run that opens its run screen, a player with none sees the invitation and the
new-campaign card, and a run with missing content is muted and cannot be opened.

## Acceptance criteria
- AC1: Every run the player is a member of appears once, in one list, newest first (← D2).
- AC2: A card shows cover-art placeholder, campaign title, status badge, teaser, the "Adventure n of m · 1 player ·
  Created <relative date>" line and a "Begin" (new) or "Resume" (in progress) button that opens the run screen (← D11).
- AC3: With no runs, the invitation copy and the prominent new-campaign button replace the list (← D8, D12).
- AC4: An unavailable run renders muted with no open button; activating it explains why and navigates nowhere (← D7).
- AC5: The greeting "Welcome back, <name>." and its run-counting subtitle read as in the design (← D11).
- AC6: The old landing screen and its greeting no longer exist, and nothing still imports them.

## Decisions
← D2, D7, D8, D11, D12

## Assumptions
- Relative dates use the platform's own formatter, no date library.
- The player count comes from the read, not a constant.
- The new-campaign button is inert until 09; finished runs show "Resume" until 08 sorts them under Archived.

## Out of scope
No tags or filtering (08) · no select dialog (09) · no archive, unarchive, rename or sharing.
