---
author: fhit:architect
owner: agent
created: 2026-09-17
---
# Research: sprint 003/02 — a campaign run and its owner

## Facts

**Blocker.** Sprint 01 is *not* in this branch's history (`git merge-base --is-ancestor
sprint/003-01-shared-database-fixture HEAD` → no; `backend/tests/database.py` and
`backend/tests/playthrough/` are absent here, present on `sprint/003-01-shared-database-fixture`).
Every AC rides on `playthrough_db`, so 01 must land in this branch's base first.

**Fixture contract (from 01's branch).** `tests/database.py:90` `scratch_db(**env_pins)` — generator,
`pytest.skip` when no server, scratch database `test_<hex>`, pins `DATABASE_URL`, runs `alembic upgrade head`
as a **subprocess** (`cwd=BACKEND_ROOT`, because `env.py` calls `fileConfig()`), yields an `AsyncSession` on
its own engine, drops `WITH (FORCE)`. `tests/playthrough/conftest.py:12` `playthrough_db` = `scratch_db()`,
no pins. Suite has no `pytest-asyncio`: each test wraps one `asyncio.run(...)`
(`tests/srd/test_database_harness.py:22`). Real-database assertions read `information_schema` /
`pg_extension` through `session.execute(text(...))` (`.../test_database_harness.py:23`-`31`), never an
inspector.

**Model conventions.** `Base` carries the naming convention (`app/core/db.py:19`-`29`). Ids are
`ID_TYPE = CHAR(26)` + `default=generate_id` (`app/core/ids.py:12`-`17`), declared as
`Mapped[str] = mapped_column(ID_TYPE, primary_key=True, default=generate_id)` (`modules/users/models.py:13`).
No mixins, no base timestamp class, no ORM relationships: every column is spelled out per model
(`modules/srd/models.py:25`-`33`). Timestamps: `DateTime(timezone=True), server_default=func.now()`
(`users/models.py:16`). Cascade precedent: `ForeignKey("users.id", ondelete="CASCADE"), index=True`
(`auth/models.py:17`-`19`). `srd` puts a composite/dialect index *outside* the class as a module-level
`Index(...)` (`srd/models.py:36`); no `__table_args__` exists in the tree yet.

**`ck` naming is a trap.** The convention is `ck_%(table_name)s_%(constraint_name)s`
(`core/db.py:22`), so a `CheckConstraint` must be given the **short** name — `name="status"` renders
`ck_campaign_runs_status` (SQLAlchemy 2.0.52, context7 `/websites/sqlalchemy_en_20_core`). Passing the full
name would render `ck_campaign_runs_ck_campaign_runs_status`. This applies **inside the migration too**:
Alembic 1.19.2 builds `op.create_table`'s ad-hoc table on a `MetaData` carrying `target_metadata`'s
convention (local source, `alembic/operations/schemaobj.py::SchemaObjects.metadata`). `pk`/`uq`/`fk`/`ix`
have no `constraint_name` token, so those keep the repo's explicit full names (`0001_baseline.py:36`-`62`).

**Alembic.** `env.py:12`-`15`: "A new module adds one line here. No autodiscovery." — alphabetical block of
`from app.modules.<m> import models as <m>_models  # noqa: F401`. Chain: `0001` (users, sessions) → `0002`
(`revision = "0002"`, `down_revision = "0001"`, `alembic/versions/0002_srd_rules.py:22`-`23`). **`0003`,
`down_revision = "0002"`.** House style: module-level `ID_TYPE = sa.CHAR(26)`, `sa.Column(...)` list, then
`sa.PrimaryKeyConstraint/UniqueConstraint/ForeignKeyConstraint(..., name=...)`, `op.create_index` separately,
`downgrade()` in exact reverse.

**Migration tests are engine-free** (`tests/srd/test_migration_0002.py`): load the revision file by
`importlib.util.spec_from_file_location`, monkeypatch each `migration.op.<fn>` with a recorder, assert
`revision` / `down_revision` and the exact ordered call list. Model tests read
`Model.__table__.columns[...]` and assert type, length, nullability, `server_default`
(`tests/srd/test_models.py:12`-`88`). Both run under plain `make backend-test`.

**Targets.** `make backend-test` = `pytest` (`--no-deps`); `make backend-test-db` = `pytest -m database`
(`Makefile:61`,`:66`). `markers = ["database: ...]`, `filterwarnings = ["error"]`, ruff line-length 100
(`backend/pyproject.toml:53`-`64`).

## Work items

- **WI1 — the module** (backend-python): `backend/app/modules/playthrough/__init__.py`, `models.py`
  (`CampaignRun`, `CampaignRunMember`), `README.md`, the one `env.py` import line, plus
  `backend/tests/playthrough/test_models.py` in `tests/srd/test_models.py`'s style. Owns `env.py` alone.
- **WI2 — the revision** (backend-python): `backend/alembic/versions/0003_campaign_runs.py` and
  `backend/tests/playthrough/test_migration_0003.py` in `test_migration_0002.py`'s style. Touches no file
  WI1 touches; parallel with WI1 given the interface below.
- **WI3 — the acceptance tests** (backend-python): `backend/tests/playthrough/test_acceptance_campaign_run_and_owner.py`,
  AC1–AC4 as `@pytest.mark.database` tests over `playthrough_db`, raw SQL through `session.execute(text(...))`.
  Authorable in parallel, **verifiable only after WI1 and WI2 merge** — schedule it last.

## Interfaces

`revision = "0003"`, `down_revision = "0002"`, file `0003_campaign_runs.py`.

`campaign_runs` — PK `pk_campaign_runs`:

| column | type | null | default / constraint |
|---|---|---|---|
| `id` | `CHAR(26)` | no | model `default=generate_id` |
| `campaign_id` | `VARCHAR(64)` | no | no FK |
| `content_version` | `VARCHAR(16)` | no | |
| `title` | `VARCHAR(120)` | **yes** | |
| `status` | `VARCHAR(16)` | no | `server_default "active"`; `CheckConstraint("status IN ('active','archived','finished')", name="status")` → `ck_campaign_runs_status` |
| `model` | `VARCHAR(64)` | yes | |
| `temperature` | `NUMERIC(3,2)` | yes | |
| `personality_prompt_id` | `VARCHAR(128)` | yes | |
| `system_prompt_override` | `TEXT` | yes | |
| `created_at` | `TIMESTAMPTZ` | no | `server_default=func.now()` |
| `updated_at` | `TIMESTAMPTZ` | no | `server_default=func.now()`; **`onupdate=func.now()` in the model only** — it is client-side, so the migration carries no trigger and no `onupdate` |

No index beyond the PK. No owner column.

`campaign_run_members` — PK `pk_campaign_run_members`:

| column | type | null | default / constraint |
|---|---|---|---|
| `id` | `CHAR(26)` | no | `default=generate_id` |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id` `ON DELETE CASCADE`, name `fk_campaign_run_members_campaign_run_id_campaign_runs` |
| `user_id` | `CHAR(26)` | no | FK → `users.id` `ON DELETE CASCADE`, name `fk_campaign_run_members_user_id_users` |
| `role` | `VARCHAR(16)` | no | `server_default "owner"`; `CheckConstraint("role IN ('owner')", name="role")` → `ck_campaign_run_members_role` |
| `created_at` | `TIMESTAMPTZ` | no | `server_default=func.now()` |

Plus `UniqueConstraint("campaign_run_id", "user_id", name="uq_campaign_run_members_campaign_run_id")` and
`op.create_index("ix_campaign_run_members_user_id", ...)` (model: `index=True` on the column).
`upgrade()` creates `campaign_runs` then `campaign_run_members` then the index; `downgrade()` reverses.

**WI3 gotcha:** run `alembic downgrade …` the way the fixture runs `upgrade` — `subprocess.run(["alembic",
"downgrade", …], cwd=BACKEND_ROOT)` — and `await playthrough_db.rollback()` first, or the session's open
transaction blocks `DROP TABLE`.

## Open questions

*technical* — **AC4 contradicts itself**: `alembic downgrade base` drops `users`, `sessions` and `srd_rules`
too, so it cannot "leave only" them. Read as two assertions: `downgrade 0002` leaves exactly the baseline +
`srd_rules` and none of ours, then `downgrade base` succeeds. Implementer should follow that reading.

*product-visible* — none.
