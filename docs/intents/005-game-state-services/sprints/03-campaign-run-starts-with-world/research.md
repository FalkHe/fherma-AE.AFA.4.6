---
author: fhit:architect
owner: agent
created: 2026-09-18
---
# Research: sprint 03

## Facts

**Routing.** `api/v1/router.py:7`-`10` mounts one bare `APIRouter()` per module under `/api/v1` (`main.py:35`,
`users/routes.py:7`). `CurrentAuth` (`auth/dependencies.py:37`) resolves the session cookie; `CsrfAuth` (`:47`) adds
the `X-CSRF-Token` check. CORS allows `GET, POST, OPTIONS` only (`main.py:28`).

**Wire shape.** `CamelModel` (`core/schemas.py:7`) — `alias_generator=to_camel, populate_by_name=True,
from_attributes=True` — on request and response both. FastAPI 0.141.1 / pydantic 2.13.5 (`backend/uv.lock`) serialise
a `response_model` by alias by default (`frontend/src/api/schema.d.ts:140`).

**Errors.** One envelope, built by `register_error_handlers` (`core/errors.py:92`-`142`) from `ApiError(code)`
(`:69`); status and message per code live in `_ERROR_INFO` (`:43`). Domain codes are the one shared `ErrorCode` enum
(`:17`), which has `NOT_FOUND` = 404 (`:50`). Module hierarchies are precedent: `srd/errors.py:1`, `content/errors.py:1`.

**Session.** `DbSession` (`core/db.py:52`); tests override it with `object()` (`tests/conftest.py:69`-`84`) and
monkeypatch the pinned service module instead, with `make_user`/`make_session` (`tests/factories.py:19`) stubbing
auth. Real database: `scratch_db()` (`tests/database.py:90`) behind the `playthrough_db` fixture
(`tests/playthrough/conftest.py:12`), `@pytest.mark.database`, one `asyncio.run(...)` per test — no `pytest-asyncio`,
`filterwarnings = ["error"]`.

**Content.** `content/service.py:58` `list_versions(campaign_id)` returns versions ascending and raises
`ContentNotFoundError` for an unknown campaign — `[-1]` is the pin (← 003-D7: the version is invisible to the player).
`:73` `load_campaign(...) -> LoadedCampaign` gives `.campaign.adventures` (order), `.adventures[aid].scenes[]
.placements[]` and `.object_templates[id]` (`content/schemas.py:79`-`152`); a `Placement` has `template, count,
carries[]`, a `Carried` has `template, count`. `greenhollow/v1` implies 13 object rows over 3 scenes of 1 adventure.

**Instance key** (003 `decisions/model.md:412`-`418`, verbatim): "`<source_adventure_id>:<source_scene_id>:
<template_id>:<ordinal>` for a placement (ordinal `1..count`, so `count: 3` yields three keys) and
`<owner_key>/<template_id>:<ordinal>` for a carried instance — both derived from authored content … Uniqueness is
carried by `uq_objects_campaign_run_id` either way." That is `UniqueConstraint("campaign_run_id", "instance_key")`
(`playthrough/models.py:126`) — the idempotency guard; a repeated start raises `IntegrityError`, no pre-check.

**Objects after `0007`.** Written per row: `campaign_run_id, kind, template_id, instance_key, name` (copied, 003
ASSUMPTION 10), `source_adventure_id, source_scene_id`; creature rows also `max_hp`/`current_hp` (equal),
`armour_class`, `is_alive=True` from `stat_block`. **NULL on creation:** `adventure_run_id` and `scene_id` (nothing is
positioned, ← D3), `member_id` (no character yet), the four creature stats on item/fixture rows
(`ck_objects_stats_creature_only`, `models.py:128`), and `campaign_runs`' four per-run overrides (← 003-D6).
`owner_object_id` is set only on carried rows and forbids a position (`ck_objects_carried`, `:142`); `state` defaults
`'{}'`. `0007` (`alembic/versions/0007_lifecycle_and_event_types.py:42`-`60`) widened the status CHECK to the five
values with `server_default 'setup'` and made `template_id` nullable.

**Relations.** Members, adventure runs, objects and events hang off `campaign_runs` with `ON DELETE CASCADE`;
`objects.member_id → campaign_run_members.id`, `objects.owner_object_id → objects.id` (`models.py:52`-`180`). There
are **no ORM relationships**, so nothing sorts inserts: carried rows must be flushed after their owners.

## Work items

WI1–WI4 run in parallel against the interfaces below, as 003 did
(`tests/playthrough/test_acceptance_campaign_run_and_owner.py:1`-`21`). Only WI5 is sequential — it describes what
landed.

- **WI1 service + errors** (`playthrough/service.py`, `errors.py`, additions to `core/errors.py`): the membership gate,
  the two writes, object instantiation from the pinned campaign, the transaction boundary. AC1–AC3.
- **WI2 routes + schemas** (`playthrough/routes.py`, `schemas.py`, registration in `api/v1/router.py`): the endpoints,
  their dependencies, the wire models, the error translation. AC1, AC2.
- **WI3 route tests** (`tests/playthrough/test_routes.py`, stubbed session, service monkeypatched): status codes,
  camelCase fields, auth/CSRF/envelope paths, the foreign-run 404. AC1, AC2.
- **WI4 database acceptance** (`tests/playthrough/test_acceptance_campaign_run_starts.py`, `@pytest.mark.database`):
  the 13-key set over `greenhollow/v1`, NULL position, pinned version, no event, repeat start rejected. AC3.
- **WI5 documentation** (`playthrough/README.md` §Surface, `docs/modules/playthrough.md` §8): replace "there is none"
  with the routes and service functions. AC4.

## Interfaces

`api_router.include_router(playthrough_routes.router, prefix="/playthrough", tags=["playthrough"])`.

| Method | Path | Dep | Body | Response |
|---|---|---|---|---|
| POST | `/api/v1/playthrough/campaign` | `CsrfAuth` | `{"campaignId": str}` | 201 `CampaignRunRead` |
| GET | `/api/v1/playthrough/campaign` | `CurrentAuth` | — | 200 `list[CampaignRunRead]` |
| GET | `/api/v1/playthrough/campaign/{run_id}` | `CurrentAuth` | — | 200 `CampaignRunRead` |

`CampaignRunRead` (`CamelModel`): `id, campaignId, contentVersion, title, status, createdAt` — nothing else.
`StartCampaignRunRequest`: `campaign_id: str` (wire `campaignId`), `min_length=1, max_length=64`.

**Service** (imported as a module, called `service.f(...)`):

- `async def start_campaign_run(db, *, user_id: str, campaign_id: str) -> CampaignRun`
- `async def list_campaign_runs(db, *, user_id: str) -> list[CampaignRun]` — joined on membership, `ORDER BY
  campaign_runs.id DESC`, archived included
- `async def get_campaign_run(db, *, user_id: str, run_id: str) -> CampaignRun`
- `async def _require_member(db, *, run_id: str, user_id: str) -> CampaignRunMember` — the first call in every
  function taking a `run_id`; raises `CampaignRunNotFoundError` for unknown **and** foreign alike (← D12)

`start_campaign_run` pins `content_version = list_versions(campaign_id)[-1]`, inserts the run (`status` left to the
`setup` server default), the owner member, then the objects in **two flushes** — placements first with explicit ids,
carried rows second with `owner_object_id` set — and commits once. It appends no event.

**Errors** (`playthrough/errors.py`), each class carrying `code: ErrorCode`:

```
PlaythroughError
├── CampaignRunNotFoundError  → NOT_FOUND (404)       unknown or foreign run
├── CampaignNotFoundError     → NOT_FOUND (404)       no such content
└── CampaignRunExistsError    → ALREADY_STARTED (409)  instance-key IntegrityError
```

`CampaignNotFoundError` is raised `from` the caught `ContentNotFoundError`, so the content hierarchy never reaches
the route. `ContentInvalidError` is *not* caught — broken shipped content is an operator fault and belongs in the 500
envelope. Routes translate one way only, through one helper every later sprint reuses:
`except PlaythroughError as exc: raise ApiError(exc.code) from exc`.

**The 13 keys of `greenhollow/v1`** (AC3's set), all prefixed `goblins-of-greenhollow:`: `village-green:mira:1` +
`village-green:mira:1/shepherds-knife:1`; `village-green:bent-horseshoe:1`; `lair-maw:goblin:1|2|3`;
`lair-maw:thorn-screen:1`; `lair-hollow:goblin-boss:1` + `…/notched-cleaver:1`; `lair-hollow:goblin:1`;
`lair-hollow:wool-sack:1` + `…/stolen-fleece:1` + `…/stolen-fleece:2`. Longest: 66 characters, inside `String(160)`.

## Open questions

- **Agent-level, called.** AC2 wants `GET …/campaign/{id}` to answer `NOT_FOUND`, AC4 says "the two routes" and Out
  of scope says "no single-run state read"; sprint 04 AC3 assumes the read exists. Ship the third route returning the
  same `CampaignRunRead` — the run row, not its state — and document three.
- **Agent-level, called.** An unknown campaign id reuses `NOT_FOUND`: naming no content file is the same class of
  thing as a run that does not exist, and a second code earns nothing.
- **Agent-level, called.** `ErrorCode` has no conflict value but `USERNAME_TAKEN`; add `ALREADY_STARTED` (409).
- **Agent-level, called.** Newest-first sorts on `id DESC`, not `created_at DESC` — ULIDs are creation-ordered.
- **Cost the brief could not see.** A carried instance belongs to a placement *instance*, so `count: 3` carrying
  something yields three carried rows. `greenhollow/v1` never does it, so AC3's count holds — but the rule belongs
  here, not in sprint 06.
