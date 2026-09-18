# playthrough

Owns a player's playthrough of a campaign and who may act in it.

## Owns

- The `campaign_runs` table (`models.py`): one playthrough per row —
  `campaign_id`, `content_version`, an optional `title`, a `status` tracking
  the run's lifecycle: `setup` (the row exists, its character does not yet),
  `ready` (the character is created), `active` (the first narration is
  written), then `archived` / `finished` as before (`server_default
  "setup"`), the model settings it runs with (`model`, `temperature`,
  `personality_prompt_id`, `system_prompt_override`, all optional) and
  `created_at` / `updated_at`. No owner column — ownership lives in
  `campaign_run_members`.
- The `campaign_run_members` table (`models.py`): who may act in a run —
  `campaign_run_id` and `user_id` (each `ON DELETE CASCADE`), a `role`
  limited to `owner` (`server_default "owner"`) and `created_at`. One row
  per `(campaign_run_id, user_id)` pair.
- The `campaign_runs` / `campaign_run_members` migration
  (`alembic/versions/0003_campaign_runs.py`).
- The `adventure_runs` table (`models.py`): one row per adventure entered
  within a campaign run — `campaign_run_id` (`ON DELETE CASCADE`, no index)
  and `adventure_id`, a `status` limited to `active` / `completed`
  (`server_default "active"`), `started_at`, `completed_at` (set if and only
  if `status` is `completed`) and `updated_at`. One row per
  `(campaign_run_id, adventure_id)` pair, and at most one `active` row per
  `campaign_run_id` (a partial unique index, not a constraint). No scene
  column and no ORM relationship.
- The `adventure_runs` migration (`alembic/versions/0004_adventure_runs.py`).
- The `objects` table (`models.py`, class `GameObject` -- `Object` shadows a
  builtin): a creature, item or fixture instantiated within a campaign run.
  `campaign_run_id` (`ON DELETE CASCADE`, indexed) and an optional
  `member_id` (`ON DELETE CASCADE`, indexed, never unique -- a member may
  hold any number of things); a `kind` limited to `creature` / `item` /
  `fixture`; an optional `template_id`, absent exactly when the object was
  generated rather than instantiated from authored content; `instance_key`
  and `name`; provenance
  (`source_adventure_id`, `source_scene_id`, no FK, written once) kept
  separate from position (`adventure_run_id` `ON DELETE SET NULL`,
  `scene_id`, written on entry and every move) -- both columns of a pair or
  neither; an optional self-referential `owner_object_id`
  (`ON DELETE CASCADE`, indexed) for a carried thing, which then has no
  position of its own; the four fighting stats `current_hp`, `max_hp`,
  `armour_class`, `is_alive`, present if and only if `kind` is `creature`,
  with `current_hp` always between `0` and `max_hp`; a `state` JSONB column
  (`server_default '{}'`); `created_at` / `updated_at`. One row per
  `(campaign_run_id, instance_key)` pair. No ORM relationship. Deleting an
  `adventure_runs` row that a positioned object still points at is rejected
  by the position check, not silently cleared -- nothing in this codebase
  deletes an `adventure_runs` row, so this is a defended edge, not a live
  path.

- The `events` table (`models.py`): one row per step of a campaign run's
  transcript -- narration, player action, a requested or resolved roll, a
  question put to the player, a tool call, a scene or adventure milestone, a
  system message, or an error or warning -- `campaign_run_id`
  (`ON DELETE CASCADE`) and an optional `actor_member_id`
  (`ON DELETE SET NULL` -- the event outlives the member); an optional
  `turn_id` with no foreign key, since no turn concept exists yet; a `type`
  limited to `narration` / `player_action` / `roll_requested` / `roll` /
  `question` / `tool_call` / `scene_entered` / `adventure_started` /
  `adventure_completed` / `system` / `error` / `warning` and a `visibility`
  limited to `player` / `dm`; a non-nullable `payload`
  JSONB column with no default; optional `prompt_tokens`,
  `completion_tokens` and `cost_usd` (an exact `NUMERIC(12,6)`, never a
  float); `created_at` only -- an event is never edited after it is
  written. Indexed by `(campaign_run_id, visibility, id)` and by
  `(campaign_run_id, turn_id)`; no unique constraint and no ORM
  relationship.

## Surface

Six endpoints, mounted under `/api/v1/playthrough/campaign`, all requiring an
authenticated caller (`POST` and `PATCH` are also CSRF-guarded):

- `POST /api/v1/playthrough/campaign` with `{"campaignId": …}` — starts a
  campaign run, answering `201` and the run.
- `GET /api/v1/playthrough/campaign` — the caller's runs, newest first,
  archived ones included.
- `GET /api/v1/playthrough/campaign/{runId}` — one of the caller's runs.
- `PATCH /api/v1/playthrough/campaign/{runId}` with `{"title": …}` —
  renames the run, answering `200` and the run.
- `POST /api/v1/playthrough/campaign/{runId}/character` — creates the run's
  one player character from its pinned campaign's seed sheet and moves the
  run to `ready`, answering `201` and the character.
- `POST /api/v1/playthrough/campaign/{runId}/archive` — puts the run away
  (or, for a run still `setup`, deletes it outright — see §Owns), answering
  `204` with no body.

A run reads as `id, campaignId, contentVersion, title, status, createdAt` and
nothing else. A character reads as `id, name, currentHp, maxHp,
armourClass` and nothing else — `CharacterRead`.

Service functions (`service.py`), called as `service.f(...)`:

- `start_campaign_run` — pins the run's `content_version` for its whole
  life, makes the starter the run's owning member, and instantiates every
  object the campaign's adventures declare, all unpositioned — entering an
  adventure is a separate, later step. The player's own creature is not
  among them; it does not exist until `create_character` runs. Appends no
  event. Starting the same run twice is refused by the uniqueness of
  `objects.instance_key` rather than by an explicit check.
- `list_campaign_runs` — the caller's runs, newest first.
- `get_campaign_run` — one run by id.
- `create_character` — builds the run's one player character (`GameObject`
  with no `template_id`, owned by the caller's membership) from a
  `SeedCharacter`-shaped sheet, defaulting to the pinned campaign's own seed
  character, then one carried `item` row per sheet inventory entry through
  the same template-driven `_build_object` sprint 03 built, then moves the
  run `setup → ready`. Refuses a second character on the run
  (`CharacterExistsError`) and refuses an archived run (`RunArchivedError`).
  Appends no event; one commit.
- `rename_campaign_run` — sets the run's title. Refuses an archived run
  (`RunArchivedError`).
- `archive_campaign_run` — `ready` / `active` / `finished` move to
  `archived`; already `archived` is a no-op. A `setup` run — never given a
  character — is deleted outright instead: the run row, its membership and
  every object instantiated for it, all removed through the schema's
  `ON DELETE CASCADE` chain. There is no unarchive.
- `activate_campaign_run` — `ready → active`, already `active` a no-op,
  any other status `InvalidRunStatusError`. No route calls it: it exists for
  a later phase's first-narration step to call (← D3).
- `_require_member` — internal; every function above that takes a run id
  calls it first to check membership before doing anything else.
- `_require_writable` — internal; raises `RunArchivedError` when the run is
  `archived`. Called by `rename_campaign_run` and `create_character` before
  they touch anything.

Every service function takes the acting user and checks membership before
touching a run. A run belonging to someone else and a run that does not
exist answer identically — not found — so no one can probe for the
existence of another player's game. Errors: an unknown or foreign run and an
unknown campaign are not found; a run already started, a second character, an
archived run refusing a write, and an invalid status transition are each a
domain conflict (`ALREADY_STARTED`, `CHARACTER_EXISTS`, `RUN_ARCHIVED`,
`INVALID_RUN_STATUS`).
