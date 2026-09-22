---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 01: campaign catalogue read

## Task
Give the content module its first HTTP surface: one authenticated read returning every shipped campaign at its newest
version with id, title, summary and adventure count, mounted into the v1 router, with tests mirroring the module
one-to-one. Regenerate the committed typed API client, which today knows only health, auth and users.

## Outcome
Signed in, the campaign list answers with Greenhollow's title, teaser and adventure count; signed out, the same
request is refused.

## Acceptance criteria
- AC1: `GET /api/v1/content/campaigns` answers 200 with one entry per campaign under the content root — id, title,
  summary, adventure count — at each campaign's newest version (← D1, D11).
- AC2: An anonymous caller is refused with the standard error envelope.
- AC3: The answer is derived from the content loader alone — no table, no migration, no cache, no write path.
- AC4: Tests live under `backend/tests/content/`, cover the list and the refusal, and pass with warnings-as-errors.
- AC5: `frontend/src/api/schema.d.ts` is regenerated and committed; both lint suites and the frontend typecheck pass.

## Decisions
← D1, D11

## Assumptions
- Newest version per campaign; a campaign whose JSON fails validation is left out and logged, not fatal to the read.
- camelCase on the wire like every other route; no paging, filtering or ordering parameter.
- The client regeneration carries the whole catch-up since the users module, including the existing playthrough routes.

## Out of scope
No adventure or scene detail · no cover art · no write · no frontend change.
