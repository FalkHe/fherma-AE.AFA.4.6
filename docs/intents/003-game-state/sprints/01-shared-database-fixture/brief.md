---
author: sprint
owner: human
created: 2026-09-16
stage: draft
---
# Sprint 01: one scratch-database fixture, shared

## Outcome
The scratch-database fixture SRD shipped becomes a shared one: `tests/srd` keeps passing unchanged over it, and a
second module reaches a real, migrated database through the same helper.

## Acceptance criteria
*Both ACs are `@pytest.mark.database` tests: green under `make backend-test-db`, skipped under `make backend-test` (← D15).*
- AC1: the shared helper lands as `backend/tests/database.py` — `scratch_db(**env_pins)`, a generator yielding an `AsyncSession` on a freshly created, `alembic upgrade head`-migrated `test_<hex>` database, which restores the environment, drops the database `WITH (FORCE)` and `pytest.skip`s when no server answers. `backend/tests/srd/conftest.py` becomes a one-line `srd_db` over it with `EMBEDDING_DIMENSIONS="1536"` as its only pin, and **`tests/srd/` passes unchanged** — harness test, migration test and model tests alike.
- AC2: `backend/tests/playthrough/conftest.py` defines `playthrough_db` over the same helper with no pins, and one test proves it yields a session against a database where `alembic upgrade head` has run — that is, `srd_rules` is present, because the whole chain applies.
- AC3: `make backend-test` (`--no-deps`), `make backend-test-db` and `make lint` all pass; the `database` marker and the `backend-test-db` target are reused as they are, not redefined.

## Decisions
← D9, D14, D15

## Assumptions
- Generalised out of `srd_db`: the reachability skip, the scratch-database lifecycle, the subprocess `alembic upgrade head` (`env.py` calls `fileConfig()`, so it cannot run in-process), the own-engine session, the teardown and environment restore. Stays SRD's, passed in as a pin and asserted there: the `1536` width, the `vector` extension.
- The scratch database is renamed from `srd_test_<hex>` to a neutral `test_<hex>`; `tests/srd`'s harness test asserts the extension and the table, never the database name, so this is safe.
- `backend/tests/conftest.py`'s suite-wide rule stands untouched: the default suite still builds no engine, and only `@pytest.mark.database` tests reach a server.

## Out of scope
**Creates no table, no model and no migration, and adds no Alembic revision — it is the one sprint here that touches none.** It is not the place to start the schema: `campaign_runs` and its member row are sprint 02 · no service, route or HTTP surface anywhere in this phase.
