---
author: fhit:architect
owner: agent
created: 2026-09-19
updated: 2026-09-19
---
# Research: sprint 06 — adventures are entered and left

## Facts

**`adventure_runs`** (`playthrough/models.py:76`-`110`): `id, campaign_run_id` (FK CASCADE), `adventure_id`
(`String(64)`, no FK), `status`, `started_at`, `completed_at`, `updated_at`; no scene column.
`uq_adventure_runs_campaign_run_id` unique `(campaign_run_id, adventure_id)` — one row per adventure ever.
`uq_adventure_runs_active` (`:91`-`96`) is a **partial** unique index on `campaign_run_id WHERE status='active'`:
it forbids a second `active` row in one run; unlimited `completed` rows there and an `active` row in every other
run are permitted. CHECK `completed_at` (`:90`): `(status='completed') = (completed_at IS NOT NULL)` — both columns move together.

**Position vs provenance** (`models.py:113`-`146`): `source_adventure_id`/`source_scene_id` are written once at
instantiation (`service.py:100`-`113`), NULL for a character's seed inventory (`:60`-`63`);
`adventure_run_id`/`scene_id` are position. CHECK `position` (`:141`) — both or neither; CHECK `carried`
(`:142`-`145`) — a row with `owner_object_id` may never be positioned. Three families per run: **cast** =
`source_adventure_id=<adv> AND owner_object_id IS NULL`; **characters** = `member_id IS NOT NULL` (their `source_*`
are NULL — `create_character:271`-`293`); **carried** = `owner_object_id IS NOT NULL`, never positioned.

**`append_event`** (`service.py:376`-`445`): `run_id, type, visibility, payload, turn_id?, actor_member_id?,
usage?`; validates against `EVENT_PAYLOADS` (`schemas.py:196`); `add` + `flush`, **no commit**, no membership check.
Payload models (`schemas.py:166`-`180`): `SceneEnteredPayload{adventure_run_id, scene_id}`,
`AdventurePayload{adventure_run_id}` for both `adventure_started` and `adventure_completed`,
`ToolCallPayload{name, args, roll_ids, result: ok|refused, outcome}` — `extra="forbid"`, stored `by_alias=True`
(camelCase).

**Gates**: `_require_member` (`service.py:124`) — one query; unknown and foreign both raise
`CampaignRunNotFoundError`/NOT_FOUND. `_require_writable(run)` (`:215`) — `archived` raises `RunArchivedError`.
No `ready|active` gate exists yet; D12 needs one.

**Content**: `load_campaign(campaign_id, version)` (`content/service.py:73`) → `campaign.adventures` (ids,
`min_length=1`, `content/schemas.py:142`), `adventures[id].entry_scene` (`:122`), `scenes` keyed by ids unique
campaign-wide (`content/service.py:177`). `load_scene(campaign_id, version, scene_id)` (`:353`). `Scene.exits`
(`content/schemas.py:90`-`114`): `id` unique within its scene (R19, `content/service.py:192`), `kind`
`scene|adventure_end`, `to` set iff `scene`. `greenhollow/v1` authors exactly one adventure; `lair-hollow` carries
the only `adventure_end` exit, `leave-the-hollow`.

**Statuses today**: `setup→ready` (`create_character:310`), `ready→active` (`activate_campaign_run:357`),
→`archived` or delete (`archive_campaign_run:330`). **Nothing sets `finished`** — `use_exit` does.

## Work items

- **WI1** `enter_adventure`, its refusals and the two positioning statements — AC1, AC4 (service half).
- **WI2** the route and its read shape — AC1 (wire half).
- **WI3** `use_exit`: move, adventure end, campaign finish, recorded refusal — AC2, AC3.
- **WI4** acceptance tests AC1–AC4 against the interfaces below (05a precedent: red until the rest lands).
- **WI5** `docs/modules/playthrough.md` §5/§8 and `playthrough/README.md` — AC4's documentation half.

**Sequential**: WI1 → WI3 (same `service.py` and `errors.py`; `use_exit`'s tests need an entered adventure).
WI2, WI4, WI5 run parallel to both once the interfaces are fixed.

**Too big for one sprint — split it.** Two mechanics, a route, four error classes, two positioning statements and
two documents; 05 was already split, and both halves' research still ran to 1044 words. Line: **06a =
`enter_adventure` + route + docs (AC1, AC4)**, **06b = `use_exit` + docs (AC2, AC3)** — the line verification
already draws (06a provable over HTTP, 06b only as `@pytest.mark.database`), and it costs no parallelism, since
WI1 → WI3 is sequential anyway.

## Interfaces

**Route.** `POST /api/v1/playthrough/campaign/{run_id}/adventure`, `CsrfAuth`, no body, `201` →
`AdventureRunRead {id, adventureId, status, startedAt}`; `except PlaythroughError as exc: raise ApiError(exc.code)`.
Entry does not change the campaign run's status (← D3: the first narration does).

**`enter_adventure(db, *, user_id, run_id) -> AdventureRun`**: `_require_member` → `_get_run` → `_require_writable`
→ `ready|active` else `InvalidRunStatusError` → `load_campaign(run.campaign_id, run.content_version)` → next = first
id in `campaign.adventures` with no `adventure_runs` row in this run; none → `AdventureExhaustedError` (AC4's
re-entry refusal too) → insert `AdventureRun(status='active')`, flush, two UPDATEs, `append_event`
`adventure_started` / `player` / `{adventure_run_id}`, one commit. `IntegrityError` → `rollback` →
`AdventureActiveError`.

**Positioning**, two `UPDATE objects` in that transaction: (1) cast — `WHERE campaign_run_id=<run> AND
source_adventure_id=<adv> AND owner_object_id IS NULL SET adventure_run_id=<new>, scene_id=source_scene_id`;
(2) characters — `WHERE campaign_run_id=<run> AND member_id IS NOT NULL SET adventure_run_id=<new>,
scene_id=<entry_scene>`. (2) catches a character created before any adventure existed: it has no `source_adventure_id` to match on. Carried
rows are excluded by (1) and untouched by (2); no other row is cleared (← C4).

**`use_exit(db, *, user_id, actor_id, exit_id) -> None`** — no route in this sprint; phase 8's tool layer is its
only caller, so AC2/AC3 are driven by `@pytest.mark.database` tests calling it directly (the backlog's stated method
for route-less mechanics). Load the object by `actor_id` alone (missing → `GameObjectNotFoundError`/NOT_FOUND), then
`_require_member(run_id=obj.campaign_run_id, …)` so a foreign actor answers identically; `_require_writable`;
`ready|active`. `load_scene(campaign_id, content_version, obj.scene_id)`, match `exit_id` in `scene.exits`.
`kind='scene'` → `scene_id = exit.to`, `adventure_run_id` unchanged, `scene_entered {adventureRunId, sceneId}` at
`player`, commit. `kind='adventure_end'` → adventure run `status='completed', completed_at=now()` in one statement,
`adventure_completed {adventureRunId}` at `player`, and — `adventure_id == campaign.adventures[-1]`, read from the
**pinned content**, not the runs table — campaign run `status='finished'`; no position is touched; commit. Zero authored adventures is
unreachable: `Campaign.adventures` is `min_length=1`, so the loader refuses such content.

**The refusal that survives (AC2, ← D11).** The exit check runs before any state change. On failure the function
appends `tool_call {name:"use_exit", args:{actorId, exitId}, rollIds:[], result:"refused", outcome:{reason}}` at
`dm`, **commits**, then raises. `append_event` only flushes, so without that commit the caller's rollback erases the
record; nothing else is pending, so the commit writes exactly that row.

**Errors** (new `ErrorCode` members, `core/errors.py:17` + `_ERROR_INFO`, 409): `AdventureActiveError` →
`ADVENTURE_ACTIVE`; `AdventureExhaustedError` → `ADVENTURE_EXHAUSTED`; `ExitNotAvailableError` →
`EXIT_NOT_AVAILABLE`; `GameObjectNotFoundError` → existing `NOT_FOUND`.

## Open questions

- **Product-visible**: with the shipped one-adventure campaign, a second `POST …/adventure` answers
  `ADVENTURE_EXHAUSTED`, never `ADVENTURE_ACTIVE` — the exhausted check precedes the insert, so AC1's
  `IntegrityError` path is only reachable in a campaign authoring two or more adventures, and its test needs a
  fixture campaign (`CONTENT_ROOT` is a module constant, `content/service.py:16`). Confirm both refusals are wanted.
- *Agent-level*: a successful `use_exit` also records `tool_call result:"ok"` at `dm` (mechanics.md's legend; D11
  puts pass/fail there). Call: yes, for `use_exit` only — `enter_adventure` is a route, not a tool.
- *Agent-level*: mechanics.md lists `finish_campaign_run` as a lifecycle function, but `use_exit` is its only
  caller. Call: inline the transition; no new public function until something else needs one.
- *Agent-level*: the signature stays exactly as AC2 pins it — no `turn_id` parameter; phase 8 adds one when a turn
  exists.
- *Agent-level*: an actor with no position (NULL `scene_id`) is the same refusal, recorded and raised as
  `ExitNotAvailableError`. One error class, not two.
