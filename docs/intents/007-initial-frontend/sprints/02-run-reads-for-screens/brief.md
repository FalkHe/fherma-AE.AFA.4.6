---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 02: run reads for the screens

## Task
Add two read-only endpoints to the playthrough module: an enriched list of the caller's runs carrying campaign title
and summary, status, created date and adventures completed of total; and one aggregate overview per run adding its
players with a ready flag and character name, and its adventures in campaign order with title, an intro excerpt and a
per-run status. A run whose pinned campaign content can no longer be loaded is still listed, flagged unavailable and
carrying no campaign copy. Regenerate the typed API client.

## Outcome
For a signed-in player the run list shows each run's campaign title and "0 of 3" adventures, one run's overview shows
the owner with no character yet plus all three adventures with their statuses, and a run pointing at removed content
is still listed and marked unavailable.

## Acceptance criteria
- AC1: The list answers, per run, campaign title and summary, status, created date, adventures completed and
  adventures total; newest first, archived runs included (← D11).
- AC2: A run whose pinned campaign or version no longer loads is present with an unavailable flag and no campaign
  copy; nothing raises (← D7).
- AC3: The overview answers the run, its members with username, role, a ready flag and the character's name when one
  exists, and its adventures in the campaign's own order with id, title, intro excerpt and a done / active / unplayed
  status (← D9, D11).
- AC4: Both are reads — no commit, no status change, no event; a non-member is refused exactly as the module's
  existing reads refuse.
- AC5: `schema.d.ts` regenerated and committed; the existing run schema is untouched, so every earlier caller still
  compiles.

## Decisions
← D1, D7, D9, D11

## Assumptions
- The ready flag means the member owns a character, not that the run status is `ready`.
- Adventure status comes from the adventure-run rows: completed → done, active → active, otherwise unplayed;
  "completed of total" counts the done ones.
- The intro excerpt is clipped server-side; "Next up" / "Waiting on party" wording stays in the frontend — the API
  states facts only.
- Users have no e-mail or display name, so the overview carries the username and nothing else about identity.
- The two reads are new schemas beside the existing run schema; their paths cannot collide with a run id.

## Out of scope
No adventure entry, no Start · no writes, invite, unarchive or rename · no frontend. If the sprint runs long, split
after the list read and ship the overview separately.
