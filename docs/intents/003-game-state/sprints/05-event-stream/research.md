---
author: fhit:architect
owner: agent
created: 2026-09-17
---
# Research: sprint 003/05 — event stream

## Facts

**Carried, not re-derived** — every convention in `sprints/04-objects-and-position/research.md` holds: the
naming convention (`app/core/db.py:19`-`29`), composite names spelled out, CHECK `name=` short, the
engine-free test styles, `alembic/env.py:14` already importing `playthrough.models`.

**AC1 is provable as written.** `generate_id()` is `str(ULID())` (`app/core/ids.py:16`-`17`); python-ulid
**4.0.1** (`backend/uv.lock:847`-`848`, source read locally in the image) routes that through
`default_generator` (`ulid/__init__.py:274`, `:238`), a lock-guarded `ULIDGenerator` (`:187`) whose default
policy is `StrictMonotonicPolicy` (`:177`-`178`): a second id in the same millisecond is the previous
randomness **+ 1** (`:83`-`93`), not fresh entropy. Measured in the image: 2000 ids, 203 of them inside one
millisecond, `ids == sorted(ids)`. Exhausting 2^80 in one millisecond raises (`:130`) — unreachable.
Crockford base32 is ASCII-ascending; the scratch database collates `en_US.utf8`, and `ORDER BY id` over
3000 random 26-char Crockford strings in a `CHAR(26)` column matched Python's byte sort exactly — executed
against pg16, not assumed.

**So the test is not flaky if it mints its own ids.** No server default exists for `id`; the acceptance
suite writes raw SQL, so it calls `generate_id()` once per row, in write order, in one process — exactly
the monotonic path. It must not assert on `created_at`: `now()` is *transaction-start*, and three rows
inserted in one transaction came back with one identical timestamp (measured, pg16). That is the point of
AC1 — the id is the only ordering.

**`turn_id` has no referent yet.** Nothing named turn exists in `backend/app`. It is a bare `CHAR(26)`, no
FK, no table, and nothing writes it this sprint; AC4 mints values with `generate_id()`. **`CHAR` pads on
read** (measured): a literal `'turn-1'` returns with 20 trailing spaces, so a `GROUP BY turn_id` assertion
against a short literal fails. Use full 26-character ids.

**AC4 is an exact decimal assertion.** The driver is psycopg3 (`postgresql+psycopg`,
`backend/tests/database.py:60`); `SUM(numeric)` is `numeric` and arrives as `decimal.Decimal`. Measured:
`0.000001 + 0.123456 + 1.000002` → `Decimal('1.123459')`, equal to `Decimal("1.123459")`. Assert against
`Decimal`, never a float and never `str()` — `Decimal` equality ignores trailing-zero scale, `str()` does
not. `Numeric` is already imported in `models.py:11` (`temperature`).

**JSONB precedent, sprint 04**: `from sqlalchemy.dialects.postgresql import JSONB`
(`alembic/versions/0005_objects.py:12`, `models.py:17`). `state` carries `server_default '{}'::jsonb`;
`payload` gets **none** — `model.md:436` declares no default and a body is always written.

## Work items

Same three-way split as 02–04; all backend-python, parallel given the interfaces below.

- **WI1 — the model**: `Event` in `backend/app/modules/playthrough/models.py`, the `README.md` "Owns"
  section, and `backend/tests/playthrough/test_models.py` in its own style.
- **WI2 — the revision**: `backend/alembic/versions/0006_events.py` and
  `backend/tests/playthrough/test_migration_0006.py`, copying `test_migration_0005.py`'s recorder exactly.
- **WI3 — the acceptance tests**: `backend/tests/playthrough/test_acceptance_event_stream.py` — AC1–AC5 as
  `@pytest.mark.database` tests over `playthrough_db`, raw SQL, no model import.

## Interfaces

`revision = "0006"`, `down_revision = "0005"`, file `0006_events.py`, module-level `ID_TYPE = sa.CHAR(26)`.

`events` — PK `pk_events`. Columns in this order:

| column | type | null | default / constraint |
|---|---|---|---|
| `id` | `CHAR(26)` | no | `default=generate_id`; no sequence column exists |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id` **`CASCADE`** |
| `actor_member_id` | `CHAR(26)` | yes | FK → `campaign_run_members.id` **`SET NULL`** |
| `turn_id` | `CHAR(26)` | yes | no FK |
| `type` | `VARCHAR(32)` | no | no default |
| `visibility` | `VARCHAR(8)` | no | no default |
| `payload` | `JSONB` | no | **no** `server_default` |
| `prompt_tokens` · `completion_tokens` | `INTEGER` | yes | — |
| `cost_usd` | `NUMERIC(12,6)` | yes | model annotation `Mapped[Decimal \| None]` (`from decimal import Decimal`), not `float` |
| `created_at` | `TIMESTAMPTZ` | no | `server_default=func.now()`; **no `updated_at`**, no `onupdate` |

In `__table_args__`, and after the columns in `op.create_table`, in order:

1. `name="type"` → `ck_events_type`: `type IN ('narration','player_action','roll','tool_call','error')`
2. `name="visibility"` → `ck_events_visibility`: `visibility IN ('player','dm')`
3. `Index("ix_events_campaign_run_id_visibility_id", "campaign_run_id", "visibility", "id")`
4. `Index("ix_events_campaign_run_id_turn_id", "campaign_run_id", "turn_id")`

**Exactly two indexes** (`model.md:444`-`448`): no `index=True` on any column — the convention would render
both composite names as `ix_events_campaign_run_id` and collide. No unique constraint. No ORM relationship.
The migration spells out `sa.PrimaryKeyConstraint("id", name="pk_events")` and both
`sa.ForeignKeyConstraint(...)`, named `fk_events_campaign_run_id_campaign_runs` and
`fk_events_actor_member_id_campaign_run_members`.

`upgrade()` = `create_table("events", ...)`, then `create_index` in order
`ix_events_campaign_run_id_visibility_id`, `ix_events_campaign_run_id_turn_id`. `downgrade()` = those two
`drop_index(..., table_name="events")` reversed, then `drop_table("events")`.

**AC5's undo assertion names the revision it undoes: `alembic downgrade 0005`, never `-1`** — `-1` resolves
against the database's newest revision and silently changes meaning when sprint 06 lands. Carried verbatim
from `test_acceptance_objects_and_position.py:491`-`509`, including the `rollback()` of the fixture's open
transaction before the subprocess runs.

SQLAlchemy 2.0.52 · Alembic 1.19.2 · python-ulid 4.0.1 · psycopg3 · pg16 (`backend/uv.lock`,
`compose.yaml:76`) — ULID, collation, `CHAR` padding, `now()` and `SUM(numeric)` behaviour all measured
locally against the running database and the installed package, not looked up.

## Open questions

*product-visible* — none. AC1–AC5 cover every rule `model.md:422`-`457` states for this table.

*technical* — none blocking. Two resolved above and recorded so the two authors cannot drift: `payload`
takes no `server_default` (unlike sprint 04's `state`), and `cost_usd` is annotated `Decimal`, deliberately
diverging from `temperature`'s `Mapped[float | None]` at `models.py:37` — that annotation is wrong for a
`Numeric` column, and AC4 turns on the value being a `Decimal`. Correcting `temperature` is not this
sprint's business.
