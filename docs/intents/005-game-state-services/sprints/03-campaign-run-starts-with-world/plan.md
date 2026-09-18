---
author: sprint
owner: agent
created: 2026-09-18
---
# Plan: Sprint 03

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Starting a campaign run: it pins the content version, gives its starter the owning membership, brings every object the campaign declares into being unplaced; listing a user's runs; reading one. Access is by membership, and another's run looks exactly like one that does not exist | AC1–AC3: `setup`, version pinned; one object per placement and per carried item, none positioned, no event; a repeat start refused by the key, not a pre-check; unknown campaign and foreign run raise their own errors | – |
| 2 | backend-python | The three endpoints over that service, in the wire's vocabulary, every failure leaving as the one error envelope | AC1, AC2: 201 and the camelCase body; unauthenticated and CSRF-less calls refused; unknown campaign and foreign run answer the envelope; the list holds only the caller's runs, newest first | WI1, I1–I5 |
| 3 | backend-python | Module README and the playthrough doc replace "there is no surface" with the endpoints and service functions | AC4: prose matches I1–I4 | I1–I5 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I5 |

## Interfaces
- I1 Registration: `api_router.include_router(playthrough_routes.router, prefix="/playthrough", tags=["playthrough"])`.

  | Method | Path | Dep | Body | Response |
  |---|---|---|---|---|
  | POST | `/api/v1/playthrough/campaign` | `CsrfAuth` | `{"campaignId": str}` | 201 `CampaignRunRead` |
  | GET | `/api/v1/playthrough/campaign` | `CurrentAuth` | — | 200 `list[CampaignRunRead]` |
  | GET | `/api/v1/playthrough/campaign/{run_id}` | `CurrentAuth` | — | 200 `CampaignRunRead` |

- I2 `CampaignRunRead` (`CamelModel`): `id, campaignId, contentVersion, title, status, createdAt`, nothing else. `StartCampaignRunRequest`: `campaign_id: str` (wire `campaignId`), `min_length=1, max_length=64`.
- I3 Service, imported as a module, called `service.f(...)`:
  - `async def start_campaign_run(db, *, user_id: str, campaign_id: str) -> CampaignRun`
  - `async def list_campaign_runs(db, *, user_id: str) -> list[CampaignRun]` — joined on membership, `ORDER BY campaign_runs.id DESC`, archived included
  - `async def get_campaign_run(db, *, user_id: str, run_id: str) -> CampaignRun`
  - `async def _require_member(db, *, run_id: str, user_id: str) -> CampaignRunMember` — first call in every function taking a `run_id`; `CampaignRunNotFoundError` for unknown **and** foreign alike (← D12)
- I4 `playthrough/errors.py`, each class carrying `code: ErrorCode`: `PlaythroughError` ← `CampaignRunNotFoundError` (`NOT_FOUND`, unknown or foreign), `CampaignNotFoundError` (`NOT_FOUND`, no such content), `CampaignRunExistsError` (new `ALREADY_STARTED`, 409). `CampaignNotFoundError` is raised `from` the caught `ContentNotFoundError`; `ContentInvalidError` is not caught. Routes translate one way: `except PlaythroughError as exc: raise ApiError(exc.code) from exc`.
- I5 `instance_key` (003 ASSUMPTION 9): `<adventure>:<scene>:<template>:<ordinal>` for a placement, ordinal `1..count`; `<owner_key>/<template>:<ordinal>` for a carried one, per placement instance. `greenhollow/v1` implies thirteen, all prefixed `goblins-of-greenhollow:`. Uniqueness on `(campaign_run_id, instance_key)` is the idempotency guard — no pre-check. Placements flush before carried rows; no ORM relationship orders them.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_campaign_run_starts.py`, over the wire; AC3 `@pytest.mark.database`.
- AC1 → a known campaign answers the run; an unknown one answers the envelope.
- AC2 → the list holds only the caller's runs, newest first, archived included; another's run and an unknown id are alike not found.
- AC3 → `greenhollow/v1` writes exactly the thirteen keys, unpositioned, version pinned, no event; a repeat is refused.

## Order
Parallel: WI1, WI3, qa. Then: WI2.
