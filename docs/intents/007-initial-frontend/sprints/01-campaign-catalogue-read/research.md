---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 007-01 campaign catalogue read

## Facts

**Content loader.** `content/service.py:51` `list_campaign_ids() -> list[str]` (sorted directory
names under `CONTENT_ROOT/campaigns`, empty list when the tree is missing). `:58`
`list_versions(campaign_id) -> list[str]` sorted ascending by the integer after `v`, raising
`ContentNotFoundError` for an unknown campaign. `:73` `load_campaign(campaign_id, version) ->
LoadedCampaign`, raising `ContentInvalidError` with a list of rule failures. Newest version is
already expressed elsewhere as `list_versions(campaign_id)[-1]`
(`playthrough/service.py:189-190`) — reuse that, do not invent a helper.

**Adventure count.** `LoadedCampaign.adventures` is a `dict[str, Adventure]` of the deduplicated,
file-backed adventures (`content/service.py:344-350`), so `len(loaded.adventures)` is the count.
`Campaign.adventures` (`content/schemas.py:142`) is the declared id list; it equals the loaded
dict only for valid content, which `load_campaign` guarantees. Shipped tree: one campaign
`greenhollow`, version `v1`, one adventure (`backend/content/campaigns/greenhollow/v1/campaign.json:2-5`).

**Content module has no HTTP surface today** — no `routes.py`, and its README states "No table, no
route" (`content/README.md:5`). Routers are combined in `backend/app/api/v1/router.py:8-12` by
`api_router.include_router(<module>_routes.router, prefix="/<module>", tags=["<module>"])`; the app
mounts that under `/api/v1`.

**Auth.** `CurrentAuth = Annotated[AuthContext, Depends(require_auth)]`
(`auth/dependencies.py:37`). No cookie → `ApiError(ErrorCode.NOT_AUTHENTICATED)` → 401
`{"error": {"code": "NOT_AUTHENTICATED", …}}`; unknown/expired cookie → `SESSION_EXPIRED`, also 401
(`auth/dependencies.py:21-34`, `core/errors.py:18-21`). Routes declare
`responses={401: {"model": ErrorEnvelope}}` (`users/routes.py:10`, `playthrough/routes.py:49`).

**Wire schemas** subclass `CamelModel` (`core/schemas.py:7`, alias generator `to_camel`,
`from_attributes=True`); content's own models subclass frozen `ContentModel` and stay snake_case —
they are not wire types.

**Tests.** Root `backend/tests/conftest.py:77-98` gives `app` / `client` (`TestClient`, DB session
stubbed by `_stub_db_session`), `session_cookie_header(token)` (:119) and `assert_error_envelope`
(:139). A signed-in request is simulated by monkeypatching `auth_service.resolve_session` and
`users_service.get_user_by_id` to return `tests.factories.make_session/make_user`
(`tests/users/test_routes.py:17-38`). `backend/tests/content/conftest.py:297` provides
`content_root` (repoints `service.CONTENT_ROOT` at `tmp_path` via `monkeypatch.setattr` on the
module) and `build_version_dir(root, campaign_id, version, …)` (:251) to write a valid or broken
campaign. Both fixture sets are visible to a new file in `backend/tests/content/`.

**Typed client.** `make generate-api` (Makefile:86-88) runs `docker compose exec -T app-web app
openapi export > frontend/openapi.json`, then `openapi-typescript openapi.json -o
src/api/schema.d.ts` — **`exec` needs the stack up** (`make up`). Both `frontend/openapi.json` and
`frontend/src/api/schema.d.ts` are committed. Today `schema.d.ts` carries only health, auth and
`/api/v1/users/me` (lines 7, 24, 41, 58, 75) — the six playthrough routes are missing, so the
regeneration also catches those up.

## Work items

- WI1 (backend-python): add the catalogue read to the content module — a `list_catalogue()` in
  `content/service.py` returning the newest valid `LoadedCampaign` per campaign, a `routes.py` with
  the single `GET /campaigns`, mount it in the v1 router, refresh `content/README.md`'s "no route"
  line, and add `backend/tests/content/test_routes.py` covering the 200 list, the anonymous 401 and
  an invalid campaign being skipped.
- WI2 (frontend, after WI1): with the stack up, run `make generate-api` and commit the regenerated
  `frontend/openapi.json` and `frontend/src/api/schema.d.ts`; no hand edits, no hook, no component.
  Verify with `make lint` and `make frontend-typecheck`.

WI2 depends on WI1 being merged into the working tree; they cannot run in parallel.

## Interfaces

**Route** — `GET /api/v1/content/campaigns`, `async def list_campaigns(auth: CurrentAuth) ->
list[CampaignSummaryRead]`, declared with `responses={401: {"model": ErrorEnvelope}}`, registered as
`api_router.include_router(content_routes.router, prefix="/content", tags=["content"])`. No `db`
parameter beyond what `CurrentAuth` itself injects. 200 body:

```json
[{"id": "greenhollow", "title": "Greenhollow", "summary": "A hedge-village …", "adventureCount": 1}]
```

**Schema** — `class CampaignSummaryRead(CamelModel)` in `content/schemas.py` with `id: str`,
`title: str`, `summary: str`, `adventure_count: int` (serialises as `adventureCount`). No version
field in this sprint; adding one later is additive.

**Service** — `def list_catalogue() -> list[LoadedCampaign]` in `content/service.py`: for each
`list_campaign_ids()`, take `list_versions(cid)[-1]` (skip when the list is empty) and
`load_campaign(cid, version)`; catch `ContentError` per campaign, log it through
`structlog.get_logger()` (as `playthrough/service.py:68` does) and leave that campaign out. The
route maps each `LoadedCampaign` to `CampaignSummaryRead(id=loaded.campaign.id,
title=loaded.campaign.title, summary=loaded.campaign.summary,
adventure_count=len(loaded.adventures))`. Trade-off: the loader stays free of wire types at the
cost of a four-field map in the route; failure behavior is "one bad campaign disappears from the
list, logged", never a 500; blast radius is the content module plus one router line.

**401 envelope** — anonymous (no `session` cookie): status 401, body
`{"error": {"code": "NOT_AUTHENTICATED", "message": "Authentication required.", "details": null}}`.

**Tests** — `backend/tests/content/test_routes.py`. Signed-in: `monkeypatch.setattr(auth_service,
"resolve_session", …)` and `(users_service, "get_user_by_id", …)` with `make_session` / `make_user`
from `tests.factories`, request via `client.get("/api/v1/content/campaigns",
headers=session_cookie_header("a-valid-cookie"))`; content comes from the `content_root` fixture
plus `build_version_dir(content_root, …)`, never the shipped tree. Anonymous: plain
`client.get(...)` asserted with `assert_error_envelope(response, status=401,
code="NOT_AUTHENTICATED")`.

## Open questions

none
