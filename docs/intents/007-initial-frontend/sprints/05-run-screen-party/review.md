---
author: sprint
owner: human
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/50
---
# Review: Sprint 05 — Opening a run shows the campaign, who is at the table and whether their character is ready, plus an invite slot

## What changed
A run now has its own address. Opening it shows the campaign's title, description and how far along the run is,
who is sitting at the table and whether each of them has a character yet, and an empty slot for inviting another
player. The buttons that would create a character or send an invitation say, politely, that they are not built yet.

## How to check it
- Sign in, open a run's address (`/runs/<its id>`): you see its campaign title, description and a status badge, and
  a "Campaigns" link back to where you came from.
- The party section reads "0 of 1 characters ready" and shows one card with your initial, your name, an "Owner"
  badge and "No character yet".
- Click "Create character": a dialog appears reading "Be brave — this feature is in development." Close it and
  click the dashed "Invite a player · Up to six at the table" tile: the same dialog appears.
- Open an address for a run that does not exist, or someone else's run: a plain "This run could not be found."
- Cut the API connection and reload: the page offers a retry that recovers once the API answers again.

## Heads-up
- The "Campaigns" back link points at today's landing page; the campaigns page it is named after arrives in sprint 07.
- The run's status badge deliberately uses the dashboard's words — New, In progress, Archived — rather than the raw
  run status, so both screens will speak one language.
- Every player card offers "Create character", including a player who already has one. The brief lists it as part of
  every card; the design mock hid it once a character existed. Worth a second look when character creation is real.
- No adventures section yet — that is sprint 06.
- The `St3ll4` / `123qweasd/fh` account noted for reviewing the preview site no longer signs in; it was checked
  against a fresh account instead.

Brief: docs/intents/007-initial-frontend/sprints/05-run-screen-party/brief.md

## Verdict
Round 1: approve — opening a run now shows its campaign, how far along it is, everyone at the table and whether each
of them has a character yet, with an empty seat for inviting another player. The buttons for creating a character and
sending an invitation politely say the feature is not built yet, and a run that does not exist or is not yours says so
plainly instead of failing.
