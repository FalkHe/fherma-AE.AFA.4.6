---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 08

| WI | Status | Note |
|---|---|---|
| 1 | done | tag row, filter, archived card; 92 frontend tests |
| qa | – | folded into WI1's route tests |

Status: `open | running | done | failed`

## Issues
- A run whose characters exist but which has entered no adventure (`ready`) is filed under "In progress", not "New" — that is the word its own badge already shows, and the state is not reachable by a player today. Worth revisiting when character creation ships.
- The note about archived runs sits above the list rather than below it, as the design has it: the brief's Outcome says the archived run is found "under a note".
- This sprint also fixes something sprint 07's review flagged: an archived run no longer offers a "Resume" button.

## Backlog proposals
- The archived note calls them "runs" where every other line on the page says "campaigns" — a copy pass over the dashboard's vocabulary.
- Nothing in the product can archive a campaign, so the Archived tag is only reachable by editing the database.

## Verify
Round 1: changes requested — all five acceptance criteria passed; the module README still described the dashboard as it was before the tags.
Round 2: changes requested — the README rewrite stated the muting precedence backwards (availability is checked before archived status). Corrected after the verdict, but the two-round limit means the verdict stands and the merge request is a draft.
- The sprint lead had been assigning merge requests to the agent account, following the provider skill's default; AGENTS.md says merge requests always go to `f4lkh3`. Corrected on !50, !51, !52 and !53.
