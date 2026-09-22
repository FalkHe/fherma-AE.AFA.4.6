---
author: sprint
owner: human
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/55
---
# Review: Sprint 09 — "New campaign" lets a player pick a story and drops them straight at its table

## What changed
The dashboard's "Create new campaign" button is real. It opens the campaign choices, and picking one starts that
campaign and puts the player straight at its table. This is the first thing in the product the player can actually
create.

## How to check it
- On the dashboard, click "Create new campaign": a dialog headed "Select a campaign" opens, reading "Choose the story
  your party will play.", with one card per campaign showing its artwork slot, title, teaser and adventure count.
- Click a campaign: it is created and you land on its run screen.
- Go back and start the same campaign again: nothing warns or stops you, and the dashboard then shows both.
- Close the dialog without choosing: nothing is created.
- If creation fails, the dialog stays open with the reason and a "Try again"; nothing is created in the meantime.

## Heads-up
- The seeded catalogue holds one campaign, so the dialog shows a single card on the running site. That the card you
  pick is the campaign that gets started is guarded by a test using a two-campaign catalogue, checked to fail when
  the wrong one is sent.
- The failure and dismissal paths are covered by tests rather than tried on the running site, to avoid leaving a
  half-made campaign behind on the shared environment.
- The dialog's panel sits lighter than the rest of the room — the same treatment as the existing in-development
  dialog, so it is consistent, but neither matches the dark palette. Worth one pass over dialog styling.

Brief: docs/intents/007-initial-frontend/sprints/09-start-campaign-dialog/brief.md

## Verdict
Round 1: changes requested — every acceptance criterion passed, but the dialog gave no visible way to close it, only
the Escape key or a click outside, while the delivered design and the product's other dialog both show a close
control, and the module's own notes already described one as present.
Round 2: changes requested — the close control works with mouse and keyboard, closes without creating anything, and
the module's notes match what shipped. But putting it inside the dialog's title meant a screen-reader user heard the
dialog announced as "Select a campaign Close". That was corrected after the verdict — the control moved out of the
title and the name now reads exactly "Select a campaign", confirmed in a real browser — but the two-round limit means
this verdict stands, so the merge request is a draft for you to release.
