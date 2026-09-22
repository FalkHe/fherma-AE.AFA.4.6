---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 01

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The content module gains an authenticated `GET /api/v1/content/campaigns` returning every campaign at its newest valid version with id, title, summary, adventureCount; mounted in the v1 router; README "no route" line refreshed | 200 list from a temp content root; anonymous 401 NOT_AUTHENTICATED envelope; a campaign whose newest version is invalid is skipped and logged, others still listed; campaign with no versions skipped | – |
| 2 | frontend | `frontend/openapi.json` and `frontend/src/api/schema.d.ts` regenerated with the stack up via `make generate-api` and committed unchanged by hand | schema.d.ts contains `/api/v1/content/campaigns` and the playthrough routes; `make frontend-typecheck` and `make frontend-lint` pass | WI1 |
| qa | qa | Black-box acceptance tests under `backend/tests/content/test_acceptance_catalogue.py` for AC1, AC2 | see below | interfaces I1–I4 |

## Interfaces
- I1 Route: `GET /api/v1/content/campaigns`, `async def list_campaigns(auth: CurrentAuth) -> list[CampaignSummaryRead]`, `responses={401: {"model": ErrorEnvelope}}`, registered in `backend/app/api/v1/router.py` as `api_router.include_router(content_routes.router, prefix="/content", tags=["content"])`. 200 body: `[{"id": "greenhollow", "title": "Greenhollow", "summary": "…", "adventureCount": 1}]`.
- I2 Schema: `class CampaignSummaryRead(CamelModel)` in `content/schemas.py` — `id: str`, `title: str`, `summary: str`, `adventure_count: int` (wire `adventureCount`). No version field.
- I3 Service: `def list_catalogue() -> list[LoadedCampaign]` in `content/service.py`: for each `list_campaign_ids()`, newest = `list_versions(cid)[-1]` (skip when empty), `load_campaign(cid, version)`; per-campaign `ContentError` caught, logged via `structlog.get_logger()`, campaign omitted. Route maps `LoadedCampaign` → `CampaignSummaryRead(id=loaded.campaign.id, title=loaded.campaign.title, summary=loaded.campaign.summary, adventure_count=len(loaded.adventures))`.
- I4 401 envelope (anonymous, no `session` cookie): status 401, `{"error": {"code": "NOT_AUTHENTICATED", "message": "Authentication required.", "details": null}}`.
- I5 Test harness: root fixtures `client`, `session_cookie_header(token)`, `assert_error_envelope(response, status=, code=)`; signed-in = `monkeypatch.setattr(auth_service, "resolve_session", …)` + `(users_service, "get_user_by_id", …)` returning `tests.factories.make_session()/make_user()` (pattern `backend/tests/users/test_routes.py:17-38`); content = `content_root` fixture + `build_version_dir(content_root, campaign_id, version, …)` from `backend/tests/content/conftest.py`.

## Acceptance tests (qa)
- AC1 → build two campaigns in `content_root` (one with two versions, title/summary differing), signed-in GET, assert 200 and exactly the newest version's title/summary/adventureCount per id in camelCase.
- AC2 → anonymous GET → 401 with the standard envelope, code NOT_AUTHENTICATED.
- AC3, AC4, AC5 → deterministic gates (ruff, pytest warnings-as-errors, frontend lint + typecheck); AC3 by review of the diff (no models/migration change).

## Order
Parallel: WI1, qa. Then: WI2 (needs `make up`).
