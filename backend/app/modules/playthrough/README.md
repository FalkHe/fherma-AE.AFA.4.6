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

## Surface

No service, route, schema or CLI yet — this sprint delivers the tables
only. Later work items in this intent add the surface.
