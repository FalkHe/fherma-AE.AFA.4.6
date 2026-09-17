---
author: fhit:architect
owner: agent
created: 2026-09-17
---
# Research: sprint 003/03 — adventure progress that cannot contradict itself

## Facts

**Carried, not re-derived.** Every convention sprint 02 fixed still holds and is unchanged:
`Base`'s naming convention (`app/core/db.py:19`-`29`), `ID_TYPE`/`generate_id`, timestamps as
`DateTime(timezone=True), server_default=func.now()`, the engine-free model and migration test styles, the
`playthrough_db` fixture and its raw-SQL/`information_schema` house style
(`docs/intents/003-game-state/sprints/02-campaign-run-and-owner/research.md`). `alembic/env.py:14` already
imports `playthrough.models` — **this sprint adds no line there**.

**A partial unique index has no precedent here; both halves are library-standard.** `srd` is the nearest
case: a module-level `Index(...)` carrying dialect kwargs (`app/modules/srd/models.py:36`-`41`), but it is
not partial. `playthrough` already uses `__table_args__` (`app/modules/playthrough/models.py:25`,`47`-`53`),
so the index belongs **in `__table_args__`** — one place for every table-level object on the class — spelled
`Index("uq_adventure_runs_active", "campaign_run_id", unique=True, postgresql_where=text("status =
'active'"))`. `Index` accepts dialect kwargs as `<dialect>_<arg>`, and `postgresql_where` is the documented
partial-index lever (SQLAlchemy 2.0.52 — context7 `/websites/sqlalchemy_en_20_core`, confirmed in the
installed source, `sqlalchemy/dialects/postgresql/base.py:1015`-`1017`). In the revision it is a separate
`op.create_index(..., unique=True, postgresql_where=sa.text("status = 'active'"))`: `create_index` forwards
unrecognised kwargs as dialect-specific (Alembic 1.19.2, installed source
`alembic/operations/ops.py::CreateIndexOp.create_index`). `op.drop_index("uq_adventure_runs_active",
table_name="adventure_runs")` needs no predicate.

**It is an *index*, not a constraint — and that changes how AC3 must look for it.** Postgres lists
`uq_adventure_runs_campaign_run_id` in `information_schema.table_constraints`, but
`uq_adventure_runs_active` only in `pg_indexes` / `pg_class`. Both still raise `IntegrityError` on
violation, which is what the ACs assert.

**The `ck` short-name trap applies to the multi-column check too.** `ck_%(table_name)s_%(constraint_name)s`
(`app/core/db.py:22`) has no column token, so a two-column check just needs a short name chosen by hand:
`CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at")` renders
`ck_adventure_runs_completed_at`, exactly `decisions/model.md` §4.3. Passing the full name would double the
prefix, as in sprint 02. Neither side of that equality is ever NULL (`status` is `NOT NULL`), so the check
never passes by unknown-truth, and a bogus `status` with `completed_at IS NULL` satisfies it — only
`ck_adventure_runs_status` fires, which keeps AC4's two assertions independent.

**`alembic downgrade -1` is literally testable here, unlike sprint 02's AC4.** It is documented usage
(Alembic 1.19.2 — context7 `/websites/alembic_sqlalchemy`, tutorial "relative migration identifiers"), and
argparse takes the negative-number-looking token as the positional revision. The fixture leaves the scratch
database at `head` (`tests/database.py:119`-`124`), so with `0004` at head `-1` resolves to `0003`: this
table drops, sprint 02's two stay. Run it the way the fixture runs `upgrade` — `subprocess.run(["alembic",
"downgrade", "-1"], cwd=BACKEND_ROOT)` — and `await playthrough_db.rollback()` first, or the session's open
transaction blocks `DROP TABLE` (`tests/playthrough/test_acceptance_campaign_run_and_owner.py:225`-`236`).

**No user row is needed for any AC.** `campaign_runs` carries no owner column, so an adventure-run fixture
inserts a `campaign_runs` parent and nothing else — `campaign_run_members` and `users` stay out of it.

## Work items

Same three-way split as sprint 02; nothing here makes it wrong.

- **WI1 — the model** (backend-python): `AdventureRun` in `backend/app/modules/playthrough/models.py`, the
  `README.md` "Owns" section extended, plus `backend/tests/playthrough/test_models.py` extended in its own
  style (one behaviour per test, read off `__table__`; the partial index is found by name in
  `AdventureRun.__table__.indexes` and asserted `unique` with its `dialect_options["postgresql"]["where"]`).
- **WI2 — the revision** (backend-python): `backend/alembic/versions/0004_adventure_runs.py` and
  `backend/tests/playthrough/test_migration_0004.py`, copying `test_migration_0003.py`'s recorder exactly.
  Touches no file WI1 touches; parallel with WI1 given the interface below.
- **WI3 — the acceptance tests** (backend-python):
  `backend/tests/playthrough/test_acceptance_adventure_progress.py`, AC1–AC5 as `@pytest.mark.database`
  tests over `playthrough_db`, raw SQL only. Authorable in parallel, green only after WI1+WI2 land.

## Interfaces

`revision = "0004"`, `down_revision = "0003"`, file `0004_adventure_runs.py`, module-level
`ID_TYPE = sa.CHAR(26)`.

`adventure_runs` — PK `pk_adventure_runs`:

| column | type | null | default / constraint |
|---|---|---|---|
| `id` | `CHAR(26)` | no | model `default=generate_id` |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id` `ON DELETE CASCADE`, name `fk_adventure_runs_campaign_run_id_campaign_runs`; **no `index=True`** |
| `adventure_id` | `VARCHAR(64)` | no | no FK (content is files) |
| `status` | `VARCHAR(16)` | no | `server_default "active"`; `CheckConstraint("status IN ('active','completed')", name="status")` → `ck_adventure_runs_status` |
| `started_at` | `TIMESTAMPTZ` | no | `server_default=func.now()` |
| `completed_at` | `TIMESTAMPTZ` | **yes** | no default |
| `updated_at` | `TIMESTAMPTZ` | no | `server_default=func.now()`; **`onupdate=func.now()` in the model only**, never in the migration |

No scene column, no `adventure_id` index, no ORM relationship.

Also on the table, in this order inside `__table_args__` / after the columns in `op.create_table`:

- `UniqueConstraint("campaign_run_id", "adventure_id", name="uq_adventure_runs_campaign_run_id")`
- `CheckConstraint("status IN ('active','completed')", name="status")`
- `CheckConstraint("(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at")` →
  `ck_adventure_runs_completed_at`
- `Index("uq_adventure_runs_active", "campaign_run_id", unique=True, postgresql_where=text("status =
  'active'"))` — in the migration a separate `op.create_index` with the same name, `unique=True` and
  `postgresql_where=sa.text("status = 'active'")`
- the migration adds `sa.PrimaryKeyConstraint("id", name="pk_adventure_runs")` and
  `sa.ForeignKeyConstraint(["campaign_run_id"], ["campaign_runs.id"],
  name="fk_adventure_runs_campaign_run_id_campaign_runs", ondelete="CASCADE")` explicitly.

`upgrade()` = `create_table("adventure_runs")` then `create_index("uq_adventure_runs_active", ...)`.
`downgrade()` = `drop_index("uq_adventure_runs_active", table_name="adventure_runs")` then
`drop_table("adventure_runs")`. Nothing else in either.

## Open questions

*technical* — none blocking. One caveat on AC5: `-1` resolves against the database's *current* revision, not
`head`; the fixture is function-scoped and freshly upgraded, so it is safe, but the assertion must not be
moved into a test that has already downgraded the same database.

*product-visible* — none.
