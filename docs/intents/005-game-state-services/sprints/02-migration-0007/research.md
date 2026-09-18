---
author: fhit:architect
owner: agent
created: 2026-09-18
---
# Research: sprint 02 — migration 0007

## Facts

**Head is `0006`.** Chain `0001…0006`, one revision per table. Convention: file `NNNN_<slug>.py`
(`alembic.ini:4` `file_template = %(rev)s_%(slug)s`), `revision = "NNNN"` zero-padded, `down_revision` the previous —
so `0007_<slug>.py`, `revision "0007"`, `down_revision "0006"`.

**The names are not bare in the database.** `alembic/env.py:29,:53` passes `target_metadata = Base.metadata`, whose
`naming_convention` is `ck_%(table_name)s_%(constraint_name)s` (`app/core/db.py:19`-`25`). Alembic 1.19.2
(`backend/uv.lock:10`; local source `alembic/operations/schemaobj.py:188`-`197`) copies that convention onto every
table `op` builds, so the literal `name="status"` in `0003_campaign_runs.py:54` reaches Postgres as
`ck_campaign_runs_status` — verified by rendering the chain offline (`alembic upgrade head --sql`).
`op.drop_constraint("status", "campaign_runs", type_="check")` and `op.create_check_constraint("status",
"campaign_runs", …)` expand through the same convention — verified by rendering both: they emit
`DROP CONSTRAINT ck_campaign_runs_status` / `ADD CONSTRAINT ck_campaign_runs_status`. **Drop-and-recreate under the
same bare name is therefore safe and exact**; the DDL runs inside the migration's transaction, and `ADD CONSTRAINT`
re-validates existing rows, which a widened set always passes.

**Current constraints.** `ck_campaign_runs_status CHECK (status IN ('active','archived','finished'))` with
`server_default 'active'` — `0003_campaign_runs.py:34,:54`, mirrored in `models.py:31,:37`; `downgrade` only drops the
tables (`0003:95`-`98`). `objects.template_id` `String(64) NOT NULL` — `0005_objects.py:32`, `models.py:156`;
`ck_objects_stats_creature_only` and `ck_objects_hp_range` at `0005:89`-`101`. `ck_events_type CHECK (type IN
('narration','player_action','roll','tool_call','error'))` and `ck_events_visibility CHECK (visibility IN
('player','dm'))` — `0006_events.py:57`-`60`, `models.py:191`-`193`; `downgrade` drops indexes then the table
(`0006:70`-`73`). `0004`/`0005`/`0006` downgrades are table drops, so nothing before `0007` ever restored a constraint.

**Tests.** `test_migration_0003.py`…`_0006.py` are engine-free: they load the revision file with `importlib`
(`0003:19`-`24`) and monkeypatch `op.create_table/create_index/drop_index/drop_table` with recorders
(`0003:27`-`42`), then assert the `sa.Column` / `sa.CheckConstraint` objects passed in. They never see a database, so
they assert the **bare** names (`0003:101`). A `0007` that calls `drop_constraint` / `create_check_constraint` /
`alter_column` needs those four names added to its own recorder list.

**Real-database tests** use `playthrough_db` (`tests/playthrough/conftest.py:12`-`14`), a no-pin wrapper over
`tests/database.py:90` `scratch_db(**env_pins)`: creates `test_<hex>`, pins `DATABASE_URL`, runs `alembic upgrade
head` **as a subprocess** from `BACKEND_ROOT`, yields an `AsyncSession`, drops the database on teardown. A downgrade
test therefore already has a working recipe — `test_acceptance_campaign_run_and_owner.py:218`-`252`: roll back the
session's open transaction *first*, then `subprocess.run(["alembic","downgrade","0002"], cwd=BACKEND_ROOT)`, then
inspect. Skipping the rollback deadlocks: `DROP CONSTRAINT` takes `ACCESS EXCLUSIVE` against a session still holding
the table.

**What pins the old values.** Old status set / default: `test_models.py:85`-`91` (default `active`), `:94`-`98`
(sqltext), `test_acceptance_campaign_run_and_owner.py:172`,`:181` (real DB, three values). Old event types:
`test_models.py:628`-`632`, `test_acceptance_event_stream.py:179`-`189` (real DB, five values, name `ck_events_type`).
`template_id NOT NULL`: `test_models.py:382`-`387`. `test_migration_0003.py:93`,`:99`-`103` and
`test_migration_0006.py` describe revision files `0007` does not touch, so they stay true and stay unchanged.

**`temperature`.** `models.py:39` is `Mapped[float | None]` over `Numeric(3, 2)` — the only mismatch; `cost_usd` next
to it is already `Mapped[Decimal | None]` (`models.py:211`). Ripple is three places and no runtime code: the
annotation, `test_models.py:108`-`113` (asserts only precision/scale today — add `python_type is Decimal`, the shape
`test_models.py:669`-`676` already uses for `cost_usd`), and `docs/modules/playthrough.md:73`. No service, route or
schema reads it; `test_acceptance_campaign_run_and_owner.py:158` only asserts `None`.

**Docs to correct.** `playthrough/README.md:9` (status set + default), `:34` (`template_id`), `:55` (five types);
`docs/modules/playthrough.md:71`,`:78` (§3), `:202` (§7), plus `:146` and `:32` (§6, `template_id`).

## Work items

- **WI1 — the schema says what the lifecycle writes.** Revision `0007` plus the matching `models.py`, moving in
  lockstep: five statuses, default `setup`, nullable `template_id`, twelve event types, `Decimal` temperature, and a
  `downgrade` that restores all three prior CHECKs, the prior default and `NOT NULL`. Serves AC1, AC2, AC3, AC4.
  Sequential — one file pair, one migration; splitting it would let model and migration drift.
- **WI2 — proof on a real database.** New `tests/playthrough/test_acceptance_migration_0007.py`: insert without a
  status → `setup`; each of the five accepted, `paused` refused; a creature with `template_id NULL` and `member_id`
  set inserts while `stats_creature_only` / `hp_range` still bite; each of the twelve types accepted, `foo` refused;
  `alembic downgrade 0006` exits 0 and the three CHECK definitions, the default and the `NOT NULL` read back as
  `0006` left them. Serves AC1–AC4.
- **WI3 — the engine-free tests stop describing the old world.** Rewrite `test_models.py:85`-`98`, `:382`-`387`,
  `:628`-`632`, `:108`-`113`; retarget `test_acceptance_campaign_run_and_owner.py:181` and
  `test_acceptance_event_stream.py:188`; add `test_migration_0007.py` in the house recorder style. Serves AC1, AC3,
  AC4.
- **WI4 — the written schema matches the built one.** `playthrough/README.md` and `docs/modules/playthrough.md`
  §3/§6/§7 at the lines above. Serves AC4.

WI2–WI4 run in parallel once the interfaces below are fixed; none of them reads WI1's file.

## Interfaces

- Revision: `0007`, `down_revision = "0006"`.
- `ck_campaign_runs_status` — `status IN ('setup','ready','active','archived','finished')`, `server_default 'setup'`.
- `ck_objects_template_id` does not exist and must not be created; `objects.template_id` simply drops `NOT NULL`.
  `ck_objects_stats_creature_only`, `ck_objects_hp_range` untouched.
- `ck_events_type` — `type IN ('narration','player_action','roll_requested','roll','question','tool_call',
  'scene_entered','adventure_started','adventure_completed','system','error','warning')`. `ck_events_visibility`
  untouched.
- `op` calls pass the **bare** name (`"status"`, `"type"`); the convention supplies the `ck_<table>_` prefix on both
  sides, so `downgrade` is byte-identical to what `0003`/`0006` emitted.
- Shared fixture entry point: `playthrough_db` (`tests/playthrough/conftest.py:13`); every test is
  `@pytest.mark.database` and wraps its own `asyncio.run(...)`.

## Open questions

- *Agent-level.* Which two "003 tests" AC1 means. **Call:** rewrite the model-level pair (`test_models.py:85`, `:94`)
  and the real-DB `for status in (...)` loop; leave `test_migration_0003.py` alone — it describes a revision file this
  sprint does not change.
- *Agent-level.* `downgrade` restores `template_id NOT NULL`, which fails on a database that already holds a
  generated character. **Call:** leave it; no such row exists before sprint 04, and a silent delete would be worse.
  State it in the revision's docstring.
- *Agent-level.* AC4 names §3/§7 only, but `template_id` is documented in §6. **Call:** correct §6 too.
- *Agent-level.* `models.py` docstrings still enumerate the old sets (`:180`, `:26`). **Call:** update with the code.
