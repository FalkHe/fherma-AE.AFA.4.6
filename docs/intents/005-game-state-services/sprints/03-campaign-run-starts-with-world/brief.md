---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 03: a campaign run starts with its world already in it

## Task
Create the `playthrough` service, error and route layer and implement the first lifecycle step: starting a campaign run — pin the content version, create the owner membership, instantiate every object the pinned campaign declares (unpositioned), and list a user's runs. Establish the per-owner access gate every later function reuses.

## Outcome
`POST /api/v1/playthrough/campaign` answers a `setup` run that pinned its content version, owns one member row and one
`objects` row per placement and carry of every adventure — none positioned yet — and `GET /api/v1/playthrough/campaign`
lists it to its owner only, while another user's or an unknown id answers the `NOT_FOUND` envelope.

## Acceptance criteria
- AC1: `POST /api/v1/playthrough/campaign {campaignId}` (CSRF-guarded, authenticated) returns 201 with the camelCase run (`id, campaignId, contentVersion, title: null, status: "setup", createdAt`); an unknown campaign answers the envelope with a stable domain code (`TestClient`, stubbed session).
- AC2: `GET /api/v1/playthrough/campaign` lists only runs the caller is a member of, newest first, archived included; a foreign or unknown `GET …/campaign/{id}` answers `NOT_FOUND`, never a distinct "forbidden".
- AC3 (`@pytest.mark.database`): starting over `greenhollow/v1` writes exactly the `instance_key` set the content implies (placements × count, carries as `owner_object_id` children), every row with `adventure_run_id`/`scene_id` NULL, `content_version` pinned, no event appended.
- AC4: `backend/tests/playthrough/` mirrors the module; `playthrough/README.md` and `docs/modules/playthrough.md` §8 replace "there is no surface" with the two routes and the service functions.

## Decisions
← D1, D3, D12 · research A1, B1/B3, C

## Assumptions
- One flat `service.py`; `_require_member(db, run_id, user_id)` first in every function, a FastAPI dependency only for route ergonomics; a `playthrough/errors.py` hierarchy mapped at the route, codes added to `core/errors.py`.
- `instance_key` follows 003 ASSUMPTION 9; the `(campaign_run_id, instance_key)` unique constraint is the idempotency guard, no pre-check.
- The four override columns stay `NULL` on creation (← 003-D6).

## Out of scope
No character (04) · nothing entered, nothing positioned (← D3, 06) · no events · no single-run state read, no scene read, no frontend, no `schema.d.ts` regeneration (phase 9).
