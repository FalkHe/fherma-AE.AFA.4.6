---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 007-02 run reads for the screens

## Facts

**Rows** (`playthrough/models.py`). `CampaignRun:31-56` — `id, campaign_id,
content_version, title, status` (`setup|ready|active|archived|finished`),
`created_at`. `CampaignRunMember:59-80` — `campaign_run_id, user_id, role`
(`owner` only). `AdventureRun:83-116` — `campaign_run_id, adventure_id, status`
(`active|completed`), unique per `(run, adventure)`. A member's character is the
`objects` row with `kind='creature'` and `member_id` set (`service.py:311-330`);
NPCs are `creature` rows with `member_id` NULL, so `member_id` separates them.

**Existing reads.** `list_campaign_runs` (`service.py:230-242`) joins membership,
`order_by(CampaignRun.id.desc())` — ULIDs are creation-ordered — archived
included; routes `:49,60` take `CurrentAuth, DbSession` and wrap the call in
`except PlaythroughError as exc: raise ApiError(exc.code) from exc`.
Authorisation is `_require_member` (`service.py:165-182`): one query, no row →
`CampaignRunNotFoundError` (`errors.py`, `code = ErrorCode.NOT_FOUND`) → 404, an
unknown id and someone else's indistinguishable on purpose (← 003-D12). A run
reads as `CampaignRunRead` = `id, campaignId, contentVersion, title, status,
createdAt` (`schemas.py:17-26`) — AC5 leaves it untouched.

**Content.** The run pins `campaign_id` + `content_version` at start
(`service.py:187-193`); reads reload it with `content_service.load_campaign(
run.campaign_id, run.content_version)` (`service.py:319,470`), raising
`ContentNotFoundError` (gone) or `ContentInvalidError` (broken), both
`ContentError` — which playthrough may import, as it already imports
`content.errors`/`content.schemas` (`service.py:24-25`). Sprint 01's catalogue
catches `ContentError` per campaign, logs it through `structlog` and omits it
(`content/service.py:367-385`): same handling, opposite outcome here — keep the
row, flag it. Copy is `loaded.campaign.title`/`.summary`
(`content/schemas.py:140-147`) and per adventure `Adventure.title`/`.intro`
(`:119-125`); `loaded.adventures` is a dict built in `campaign.adventures` order
(`content/service.py:121-127,346-352`), so iterating it *is* campaign order.
Shipped `greenhollow/v1` declares one adventure. `User.username` comes from
`app.modules.users.models`, whose import is precedented (`auth/service.py:10`),
as is a service returning a wire model (`recap` → `NarrationRead`, `:2387`).

**Tooling.** `make generate-api` (`Makefile:86-88`) exports the OpenAPI document
through `docker compose exec` (stack must be up), then runs `openapi-typescript`
into the committed `frontend/openapi.json` / `src/api/schema.d.ts`, which
already carry the nine playthrough paths. Tests: `backend/tests/playthrough/`,
`make backend-test`, warnings fatal; routes drive the root `client`,
`session_cookie_header`, `assert_error_envelope` fixtures
(`tests/conftest.py:88,120,139`) with auth and the service monkeypatched by
attribute (`tests/playthrough/test_routes.py:39-53`); service tests are
engine-free — `FakeSession` with queued `execute()` results, one
`asyncio.run(...)` per test, no pytest-asyncio (`test_service.py:63ff`) — and
take content from the shipped tree or a `monkeypatch.setattr(content_service,
"load_campaign", …)`. Only `@pytest.mark.database` tests build an engine.

**Paths.** A literal sibling of `/campaign/{run_id}` resolves only by
declaration order, so both reads go under a new `/runs` segment. Trade-off: a
second path family (`/campaign` = lifecycle, `/runs` = read model) and a rewrite
of the README's "Nine endpoints, mounted under `/api/v1/playthrough/campaign`"
(`playthrough/README.md:90-92`).

## Work items

- **WI1 (backend-python) — the list read.** `CampaignRunSummaryRead`,
  `service.list_run_summaries` with `_load_pinned`, route `GET /runs`, README
  surface section. Tests: the camelCase field set for a run with content; newest
  first, archived included; completed count from `adventure_runs`; a run whose
  content raises `ContentNotFoundError` and one raising `ContentInvalidError`
  both come back `unavailable` with null copy while a healthy sibling is
  unaffected and nothing raises; two runs of one campaign load content once;
  anonymous 401; no commit/add/execute in the route.
- **WI2 (backend-python, after WI1) — the overview read.**
  `CampaignRunOverviewRead`, `CampaignRunMemberRead`, `CampaignRunAdventureRead`,
  `service.get_run_overview` with `_excerpt`, route `GET /runs/{run_id}/overview`,
  README. Tests: members carry username and role, `ready` false with null
  `characterName` and true with the name once the character exists (an NPC row
  must not make a member ready); adventures in campaign order with
  `done`/`active`/`unplayed`; a long intro clipped at a word boundary, a short
  one verbatim; an unavailable run answers 200 with null copy and
  `adventures: []`; non-member and unknown id 404; anonymous 401.
- **WI3 (frontend, after WI1+WI2).** With the stack up, `make generate-api`;
  commit `frontend/openapi.json` and `frontend/src/api/schema.d.ts` unedited.
  Check: both paths present, `make frontend-typecheck` and `make lint` pass.

Sequential — WI1 and WI2 touch the same three files. The brief's fallback split
(ship WI1, defer WI2) falls exactly on this boundary.

## Interfaces

**I1 Routes** (`playthrough/routes.py`, same `try/except PlaythroughError` body
as the existing reads).

```python
@router.get("/runs", responses={401: {"model": ErrorEnvelope}})
async def list_run_summaries(auth: CurrentAuth, db: DbSession) -> list[CampaignRunSummaryRead]:

@router.get("/runs/{run_id}/overview",
            responses={401: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def get_run_overview(run_id: str, auth: CurrentAuth, db: DbSession) -> CampaignRunOverviewRead:
```

**I2 Service** (`playthrough/service.py`, returning the wire models directly —
routes add no mapping).

```python
async def list_run_summaries(db: AsyncSession, *, user_id: str) -> list[CampaignRunSummaryRead]
async def get_run_overview(db: AsyncSession, *, user_id: str, run_id: str) -> CampaignRunOverviewRead
def _load_pinned(run: CampaignRun) -> LoadedCampaign | None   # None on ContentError, logged
def _excerpt(text: str, limit: int = 200) -> str
```

`list_run_summaries` takes rows and order from `list_campaign_runs`, adds one
grouped `func.count()` over `adventure_runs` (`status == "completed"`) and one
over `campaign_run_members`, both keyed by `campaign_run_id`, and caches
`_load_pinned` per `(campaign_id, content_version)`. `get_run_overview` calls
`_require_member` then `_get_run`, then one query over `CampaignRunMember`
joined to `User` and outer-joined to `objects` (`member_id == member.id AND
kind == 'creature'`) ordered by member id, and one over this run's
`adventure_runs`. Reads only: no `commit`, no status change, no event.
`_load_pinned` catches `ContentError` alone, logs it
(`logger.warning("playthrough_content_unavailable", run_id=…, error=str(exc))`)
and returns `None`; anything else travels.

`_excerpt`: `text` unchanged when `len(text) <= limit`; else cut at `limit`,
drop back to the last space if there is one, `rstrip()`, append `"…"`.

**I3 Schemas** (`playthrough/schemas.py`, all `CamelModel`):

```python
class CampaignRunSummaryRead(CamelModel):
    id: str
    campaign_id: str
    status: str
    created_at: datetime
    campaign_title: str | None
    campaign_summary: str | None
    adventures_completed: int
    adventures_total: int | None
    player_count: int
    unavailable: bool

class CampaignRunMemberRead(CamelModel):
    user_id: str
    username: str
    role: str
    ready: bool
    character_name: str | None

class CampaignRunAdventureRead(CamelModel):
    id: str            # the campaign's adventure id, not the adventure_runs row id
    title: str
    intro_excerpt: str
    status: str

class CampaignRunOverviewRead(CamelModel):
    id: str
    campaign_id: str
    content_version: str
    title: str | None
    status: str
    created_at: datetime
    campaign_title: str | None
    campaign_summary: str | None
    unavailable: bool
    members: list[CampaignRunMemberRead]
    adventures: list[CampaignRunAdventureRead]
```

`ready` is `character_name is not None`. Adventure `status` maps the
`adventure_runs` row: `completed` → `done`, `active` → `active`, no row →
`unplayed`; `adventuresCompleted` counts the `done` ones. `playerCount` is the
membership count — sprint 07 reads the player line from here.

**I4 Wire, content present** (`GET /api/v1/playthrough/runs`):

```json
[{"id": "01J…", "campaignId": "greenhollow", "status": "setup",
  "createdAt": "2026-09-22T07:00:00Z", "campaignTitle": "Greenhollow",
  "campaignSummary": "A hedge-village …", "adventuresCompleted": 0,
  "adventuresTotal": 3, "playerCount": 1, "unavailable": false}]
```

**I5 Wire, content gone.** Everything the content would have supplied is
`null`, the row's own facts stay. List entry: `"campaignTitle": null,
"campaignSummary": null, "adventuresTotal": null, "unavailable": true`, with
`adventuresCompleted` and `playerCount` still counted. Overview: the same three
plus `"adventures": []`, `members` unchanged, status 200.

**I6 Refusals** — reused verbatim from the module's existing reads: anonymous →
401 `{"error": {"code": "NOT_AUTHENTICATED", "message": "Authentication
required.", "details": null}}`; non-member or unknown `run_id` → 404
`{"error": {"code": "NOT_FOUND", "message": "Resource not found.",
"details": null}}`.

## Open questions

**Product-visible:**
- The shipped campaign holds one adventure, so a real dashboard reads
  "Adventure 0 of 1", not the brief's "0 of 3". Is more campaign content wanted?
- Opening an unavailable run by typing its address answers the run, flagged
  unavailable, with no adventures. D7 only says the dashboard cannot open it —
  should the address itself refuse with not-found instead?

**Technical (agent's call):** the `/runs` path family, the 200-character intro
limit, `playerCount` riding along in the list for sprint 07.
