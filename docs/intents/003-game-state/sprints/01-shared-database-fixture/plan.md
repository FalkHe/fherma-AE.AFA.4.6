---
author: sprint
owner: agent
created: 2026-09-17
---
# Plan: Sprint 01 — one scratch-database fixture, shared

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A module-level generator that hands any test a session on a freshly created, fully migrated scratch database, and leaves nothing behind. It carries no knowledge of any one module: every environment pin is passed in by the caller. | Skips when no server answers · creates a uniquely named database · applies every migration · yields a working session · on teardown closes, restores every environment variable it pinned (removing ones that were absent) and drops the database even after a failure | – |
| 2 | backend-python | The SRD suite's own fixture becomes a one-line delegation to WI1 carrying its embedding-width pin, and the SRD tests keep passing with no change to any of them. | The four existing SRD real-database tests still pass · no SRD test file other than its fixture file changes | I1 |
| 3 | backend-python | A new test package for the playthrough module whose fixture is the same delegation with no pins at all. | The fixture is importable and resolves for tests in that package | I1 |
| qa | qa | Acceptance tests for AC1 and AC2, black-box over I1 and I2. | See below | I1, I2 (WI3's package must exist for AC2's file to collect) |

## Interfaces
- **I1** — `backend/tests/database.py`, no pytest fixture in the file:
  `def scratch_db(**env_pins: str) -> Iterator[AsyncSession]`
  A plain generator. In order: `pytest.skip` when the admin server is unreachable → create `test_<uuid4().hex[:16]>` → set `DATABASE_URL` to the scratch URL and every `env_pins` key to its value → clear the settings cache → run `alembic upgrade head` as a subprocess (`pytest.fail` with both streams on non-zero) → yield an `AsyncSession` on its own engine → in `finally`: close, dispose, restore `DATABASE_URL` and every pinned key to its prior value (pop where absent), clear the cache, `DROP DATABASE IF EXISTS "<name>" WITH (FORCE)`. `BACKEND_ROOT = Path(__file__).resolve().parents[1]`.
- **I2** — each consumer is one delegation:
  `tests/srd/conftest.py`: `@pytest.fixture def srd_db(): yield from scratch_db(EMBEDDING_DIMENSIONS="1536")`
  `tests/playthrough/conftest.py`: `@pytest.fixture def playthrough_db(): yield from scratch_db()`

## Acceptance tests (qa)
- AC1 → `backend/tests/test_shared_scratch_database.py`, `@pytest.mark.database`, driving `scratch_db(...)` directly: a session arrives on a migrated database (the SRD table is present), an arbitrary pin is visible inside and restored — including removal — afterwards, and the scratch database is gone once the generator is exhausted, also when the body raised.
- AC2 → `backend/tests/playthrough/test_acceptance_shared_fixture.py`, `@pytest.mark.database`, consuming `playthrough_db`: the session answers, and `srd_rules` exists, proving the whole migration chain ran for a module that owns no migration.
- AC3 is a gate, not a test: lint, the default suite and the real-database suite all run before the merge request.

## Order
Parallel: WI1, WI2, WI3, qa — every dependency is on an interface above, and those are fixed. Gates last.
