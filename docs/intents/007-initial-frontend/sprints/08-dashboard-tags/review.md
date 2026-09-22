---
author: sprint
owner: human
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 08 — The dashboard sorts runs under "In progress", "New" and "Archived" and opens on the one that matters

## What changed
The dashboard now sorts a player's campaigns under three tags and shows one group at a time, opening on whichever
matters most. Archived campaigns have their own tag: they are still there to look at, greyed out and with no way in,
under a line saying they are kept as they are.

## How to check it
- Sign in with a campaign under way: the dashboard opens on "In progress" showing only that one. With nothing under
  way it opens on "New" instead.
- Click "New" or "Archived": the list swaps to that group. The count in the greeting still counts everything.
- An archived campaign is greyed out, has no "Begin" or "Resume" button and cannot be opened; a line above it reads
  that archived runs are kept as they are and are view-only.
- A tag with nothing in it says so in one line, rather than showing the start-your-first-campaign invitation.
- Sign in with no campaigns at all: the invitation shows and no tags do.
- Reload the page: the dashboard opens on its own default again — the tag you picked is not remembered anywhere.

## Heads-up
- An archived campaign no longer offers a "Resume" button. That was flagged during the last sprint's review as a
  latent bug and this sprint's rules made it real, so it is fixed here.
- The line about archived campaigns calls them "runs", which is the internal word; every other line on the page says
  "campaigns". Worth a copy pass.
- Nothing in the product can archive a campaign yet, so the Archived tag is only reachable by editing the database.
  It was verified that way.
- A campaign whose party is assembled but which has entered no adventure files under "In progress" — the word its own
  badge already shows. Not reachable by a player today; worth revisiting when character creation ships.
- The note sits above the list rather than below it as the design has it, because the brief asks for the archived
  campaign to be found "under a note".

Brief: docs/intents/007-initial-frontend/sprints/08-dashboard-tags/brief.md

## Verdict
