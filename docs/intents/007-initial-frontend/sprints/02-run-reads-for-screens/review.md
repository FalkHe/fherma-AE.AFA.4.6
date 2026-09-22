---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/41
---
# Review: Sprint 02 — a player's runs can be read with everything the screens show

## What changed
A player's runs can now be read with everything the coming screens need: each run's campaign, status, created date,
adventures done of total and players at the table; opening one run adds who is at the table, whose character is
ready, and the campaign's adventures in order with what has been played. Both are reads only.

## How to check it
- Read your runs: each names its campaign, how far it has come and how many players it has — newest first, archived
  runs among them.
- Open one run: it names the players, says whose character is ready, and lists the adventures in order with what is
  done, being played, or untouched.
- Point a run at a campaign that no longer exists: it stays listed, marked unavailable, and nothing else breaks.
- Ask for a run you are not part of, and for one that does not exist: both answer alike, revealing nothing.

## Heads-up
- The shipped campaign holds one adventure, so progress reads "0 of 1", not the brief's illustrative "0 of 3".
  Seeding fuller content is separate work.
- A run with unavailable content answers when asked for directly, flagged, rather than refusing — the screens must
  read it to explain why it cannot be opened.

Brief: docs/intents/007-initial-frontend/sprints/02-run-reads-for-screens/brief.md

## Verdict
Round 1: approve — a player's runs can now be read the way the coming screens need them: each run named by its
campaign with progress, players and created date, and a single run opening with who is at the table, whose
character is ready, and the adventures in order with what has been played. Checked live against a real run,
including one pointed at content that no longer exists, which stays listed and flagged instead of breaking.
Progress reading "0 of 1" is right for the one adventure currently shipped, and keeping an unavailable run
readable is what lets the dashboard later explain why it cannot be opened — the screens must still refuse to
open it.
