# playthrough

Owns a player's playthrough of a campaign and who may act in it.

## Owns

- The `campaign_runs` table (`models.py`): one playthrough per row —
  `campaign_id`, `content_version`, an optional `title`, a `status` limited
  to `active` / `archived` / `finished` (`server_default "active"`), the
  model settings it runs with (`model`, `temperature`,
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
  `fixture`; `template_id`, `instance_key` and `name`; provenance
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

- The `events` table (`models.py`): one row per narration, player action,
  dice roll, tool call or error recorded in a campaign run's transcript --
  `campaign_run_id` (`ON DELETE CASCADE`) and an optional `actor_member_id`
  (`ON DELETE SET NULL` -- the event outlives the member); an optional
  `turn_id` with no foreign key, since no turn concept exists yet; a `type`
  limited to `narration` / `player_action` / `roll` / `tool_call` / `error`
  and a `visibility` limited to `player` / `dm`; a non-nullable `payload`
  JSONB column with no default; optional `prompt_tokens`,
  `completion_tokens` and `cost_usd` (an exact `NUMERIC(12,6)`, never a
  float); `created_at` only -- an event is never edited after it is
  written. Indexed by `(campaign_run_id, visibility, id)` and by
  `(campaign_run_id, turn_id)`; no unique constraint and no ORM
  relationship.

## Surface

No service, route, schema or CLI yet — this sprint delivers the tables
only. Later work items in this intent add the surface.
