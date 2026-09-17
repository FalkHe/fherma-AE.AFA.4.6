---
author: fhit:architect
owner: agent
created: 2026-09-17
---
# Research: sprint 003/04 — objects and position

## Facts

**Carried, not re-derived** — every convention in `sprints/03-adventure-progress/research.md` holds: the
naming convention (`app/core/db.py:19`-`29`), the engine-free test styles, the `ck` short-name trap (pass
`name="position"`, never the rendered name). `alembic/env.py:14` already imports `playthrough.models` — no
line added.

**What the content declares** (`content/schemas.py:29`-`:70`). `kind` is exactly `creature | item |
fixture`, closed by the discriminated union at `:67`-`70`. `CreatureTemplate` carries `stat_block` with
`max_hp` and `armour_class`; `ItemTemplate` only `attacks`, `FixtureTemplate` only `checks` — **neither
declares hit points or armour class**, so "all four NULL unless creature" is authored reality, not a guess.
**Nothing declares `current_hp` or `is_alive`**, not even `SeedCharacter` (`:116`-`:124`): both are
instantiation-time values, hence stored (ASSUMPTION 8).

**`greenhollow/v1` checked** (`content/campaigns/greenhollow/v1/`): 9 templates, 3 creature / 4 item / 2
fixture, every value used; 13 object rows, 4 carried (`model.md:373` says 3 — sprint 06's correction). A
carried item may hang off a **fixture** (`wool-sack` carries `stolen-fleece`), so `owner_object_id` stays a
plain self-FK, unrestricted by `kind`. Longest real `instance_key` is 62 chars, a `pc:<member_id>:<n>` key
~31 (ASSUMPTION 9, `model.md:412`-`418`): `VARCHAR(160)` is ample and **no format CHECK belongs in the
schema** — phase 5 produces it, `uq_objects_campaign_run_id` defends it.

**Provenance ≠ position** (`model.md:152`-`160`): `source_adventure_id`/`source_scene_id` are content ids
written once at instantiation, deliberately not FKs; `adventure_run_id`/`scene_id` are written on entry and
every move. Both pairs nullable, never constrained against each other.

**Three-valued logic bites twice — executed against pg16, not assumed.** A CHECK passes when it evaluates
to NULL: `CHECK (current_hp BETWEEN 0 AND max_hp)` accepted `(99, NULL)`; the strict form below refused it.
The stats and carried rules were run the same way, every AC1/AC3/AC4 case behaving as written. What keeps
them safe: every operand is `IS [NOT] NULL` or a comparison on a `NOT NULL` column.

**`ON DELETE SET NULL` on `adventure_run_id` collides with the both-or-neither check.** Deleting an
`adventure_runs` row a positioned object points at raises `ck_objects_position` — that action is an UPDATE
and CHECKs are re-evaluated (confirmed on pg16). D3 deletes nothing, so accept it: **no cascade test on that
FK**, a README sentence instead.

## Work items

Same three-way split as 02 and 03; all backend-python, parallel given the interfaces below.

- **WI1 — the model**: `GameObject` (`__tablename__ = "objects"`; `Object` shadows a builtin) in
  `backend/app/modules/playthrough/models.py`, the `README.md` "Owns" section, and
  `backend/tests/playthrough/test_models.py` in its own style.
- **WI2 — the revision**: `backend/alembic/versions/0005_objects.py` and
  `backend/tests/playthrough/test_migration_0005.py`, copying `test_migration_0004.py`'s recorder exactly.
- **WI3 — the acceptance tests**: `backend/tests/playthrough/test_acceptance_objects_and_position.py` —
  AC1 and AC3–AC5 as `@pytest.mark.database` tests over `playthrough_db`, raw SQL, no model import.

## Interfaces

`revision = "0005"`, `down_revision = "0004"`, file `0005_objects.py`, module-level `ID_TYPE = sa.CHAR(26)`,
`from sqlalchemy.dialects.postgresql import JSONB` (no precedent here).

`objects` — PK `pk_objects`. Every FK name renders `fk_objects_<column>_<referred_table>`:

| column | type | null | default / constraint |
|---|---|---|---|
| `id` | `CHAR(26)` | no | `default=generate_id` |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id` `CASCADE` |
| `member_id` | `CHAR(26)` | yes | FK → `campaign_run_members.id` `CASCADE` |
| `kind` | `VARCHAR(16)` | no | no default |
| `template_id` | `VARCHAR(64)` | no | no FK |
| `instance_key` | `VARCHAR(160)` | no | no format check |
| `name` | `VARCHAR(120)` | no | — |
| `source_adventure_id` · `source_scene_id` | `VARCHAR(64)` | yes | provenance, no FK |
| `adventure_run_id` | `CHAR(26)` | yes | FK → `adventure_runs.id` **`SET NULL`** |
| `scene_id` | `VARCHAR(64)` | yes | — |
| `owner_object_id` | `CHAR(26)` | yes | self-FK → `objects.id` `CASCADE` |
| `current_hp` · `max_hp` · `armour_class` | `INTEGER` | yes | — |
| `is_alive` | `BOOLEAN` | yes | no `default` |
| `state` | `JSONB` | no | `server_default=text("'{}'::jsonb")` |
| `created_at` · `updated_at` | `TIMESTAMPTZ` | no | `server_default=func.now()`; `updated_at` also **model-only** `onupdate=func.now()` |

In `__table_args__`, and after the columns in `op.create_table`, in order (CHECK `name=` is short; the
arrow renders):

1. `UniqueConstraint("campaign_run_id", "instance_key", name="uq_objects_campaign_run_id")`
2. `name="kind"` → `ck_objects_kind`: `kind IN ('creature','item','fixture')`
3. `name="stats_creature_only"` → `ck_objects_stats_creature_only`:
   `(kind = 'creature') = (current_hp IS NOT NULL) AND (kind = 'creature') = (max_hp IS NOT NULL) AND (kind = 'creature') = (armour_class IS NOT NULL) AND (kind = 'creature') = (is_alive IS NOT NULL)`
   — per column, so *any one* stat on an item raises; never NULL (`kind` is `NOT NULL`).
4. `name="hp_range"` → `ck_objects_hp_range`:
   `(current_hp IS NULL AND max_hp IS NULL) OR (current_hp IS NOT NULL AND max_hp IS NOT NULL AND current_hp >= 0 AND current_hp <= max_hp)`
   — never NULL; bare `BETWEEN` passes half-filled rows.
5. `name="position"` → `ck_objects_position`: `(adventure_run_id IS NULL) = (scene_id IS NULL)`
6. `name="carried"` → `ck_objects_carried`: `owner_object_id IS NULL OR (adventure_run_id IS NULL AND scene_id IS NULL)`
7. `Index("ix_objects_adventure_run_id_scene_id", "adventure_run_id", "scene_id")`

`index=True` on `campaign_run_id`, `member_id` (**never unique**, ← D13) and `owner_object_id`;
`adventure_run_id` none. No ORM relationship.

The migration spells out `sa.PrimaryKeyConstraint("id", name="pk_objects")` and the four
`sa.ForeignKeyConstraint(...)`; a self-FK is legal inside `CREATE TABLE`.

`upgrade()` = `create_table("objects", ...)`, then `create_index` in order `ix_objects_campaign_run_id`,
`ix_objects_member_id`, `ix_objects_owner_object_id`, `ix_objects_adventure_run_id_scene_id`. `downgrade()`
= those four `drop_index(..., table_name="objects")` reversed, then `drop_table("objects")`.

SQLAlchemy 2.0.52 · Alembic 1.19.2 · pg16 (`backend/uv.lock`, `compose.yaml:76`) — JSONB via context7
`/websites/sqlalchemy_en_20`; CHECK/SET-NULL behaviour from the database.

## Open questions

*product-visible* — **the absent AC2 is a numbering slip, and it leaves one gap.** ACs 1, 3, 4 and 5 cover
every constraint `model.md:394`-`421` lists — kind, the four stats, hp range, position, carried, per-run
`instance_key`, no unique index on `member_id` — so nothing about *refusing* is missing. Uncovered is the
**shape** claim sprint 03 carried as its AC1: provenance columns distinct from position ones, and a deleted
campaign run taking its objects. Recommended, owner to confirm: keep the numbering; prove shape in WI2's
migration test and WI3's opening assertion.

*technical* — none blocking, both resolved above. `model.md` names the location rule both
`ck_objects_location` (`:238`) and `ck_objects_position` (`:409`); the table section wins, **split in two**
so AC4's assertions can name which fired. `ix_objects_campaign_run_id` merely duplicates
`uq_objects_campaign_run_id`'s leading column, but is kept, staying literal to the approved model.
