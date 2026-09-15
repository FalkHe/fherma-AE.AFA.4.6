---
author: intake
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 07: an agent's state survives between two runs

## Outcome
State checkpointed under a `thread_id` by one CLI run is read back by the next,
out of the checkpointer's own schema, which Alembic leaves untouched.

## Acceptance criteria
- AC1: a setup command creates the checkpointer's tables in their own `checkpoints` schema in the existing postgres.
- AC2: a throwaway two-step graph run under a `thread_id` stops at an interrupt in one CLI invocation; a second, separate invocation resumes it and reaches the end.
- AC3: the resumed run sees the value the first run left behind — printed, so it is visible without a database client.
- AC4: `alembic revision --autogenerate` proposes nothing for the `checkpoints` schema; the exclusion is explicit in `include_object`, not incidental.
- AC5: `alembic upgrade head` on a fresh database still succeeds with the schema present.
- AC6: the test suite asserts the Alembic exclusion without building a real engine, as `backend/tests/conftest.py` requires.

## Decisions
← none directly; this enables phases 7 and 8.

## Assumptions
- `AsyncPostgresSaver` from `langgraph-checkpoint-postgres`, via `from_conn_string(...)` then `await checkpointer.setup()`; this sprint pins the `langgraph-*` floors.
- The demo graph is a test fixture, not shipped product surface.

## Out of scope
The character-creation dialogue and the DM loop that will use this (phases 7, 8)
· pgvector · any real agent state shape.
