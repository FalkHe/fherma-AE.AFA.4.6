---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/40
---
# Review: Sprint 01 — The product can list the campaigns a player may choose from, with title, teaser and number of adventures

## What changed
A signed-in player can now ask the product for the list of campaigns to choose from. Each entry carries the
campaign's title, its teaser and how many adventures it holds, always taken from the campaign's newest version.
The frontend's typed view of the API was refreshed so it now knows this list as well as the campaign-run calls it
had been missing.

## How to check it
- Sign in, then open the interactive API page and call the campaign list: Greenhollow appears once with its title,
  teaser and one adventure.
- Call the same list without being signed in: the request is refused with the usual "authentication required"
  error.
- A campaign whose newest version is broken is left out of the list and logged; the others still show.

## Heads-up
- Nothing is stored for this: the list is read straight from the shipped campaign files, so no data setup is needed.

Brief: docs/intents/007-initial-frontend/sprints/01-campaign-catalogue-read/brief.md

## Verdict
