---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 07 — an agent's state survives between two runs

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The checkpointer's packages are pinned and its connection reaches a dedicated schema | the conn string derivation is exact, including the escaped `search_path`; `make up` still starts after the dependency change | I1, I2 |
| 2 | backend-python | Alembic ignores the checkpointer's schema, deliberately rather than incidentally | `include_object` returns False for that schema and True otherwise, asserted as a pure function with no engine; both `context.configure` calls carry both keywords | I1 |
| 3 | backend-python | A throwaway graph that interrupts in one CLI run and resumes in the next | the three commands exist and map to the service; `CliRunner` with the service monkeypatched, no database | I3 · WI1 |
| 4 | backend-python | `docs/general/model.md` names the mechanism that actually exists | – (markdown only) | – |

## Interfaces
Verbatim from `research.md → Interfaces`; binding. Summarised — read that file for the full text.

- I1: `app/core/checkpointer/schema.py` — `CHECKPOINTER_SCHEMA = "checkpoints"` and `include_object(object, name, type_, reflected, compare_to) -> bool` returning `getattr(object, "schema", None) != CHECKPOINTER_SCHEMA`. **Zero third-party imports**, which is what lets `env.py` and AC6's test stay engine-free.
- I2: `app/core/checkpointer/service.py` — `checkpointer_conn_string(database_url)`, `checkpointer()`, `ensure_schema()`, `setup()`. Pinned exactly by test: `checkpointer_conn_string("postgresql+psycopg://app:app@postgres:5432/application")` == `"postgresql://app:app@postgres:5432/application?options=-csearch_path%3Dcheckpoints"`. The `+psycopg` tag must be stripped and the inner `=` must be `%3D`-escaped.
- I3: `app checkpoint setup` → `checkpoints schema ready`; `app checkpoint demo start --thread <id>` → `interrupted: <json>`; `app checkpoint demo resume --thread <id> --value <text>` → `answer: <left>|<value>`. Stdout only, exit 0 / 1.
- `env.py`: `from app.core.checkpointer.schema import include_object`, passed with `include_schemas=True` to **both** `context.configure(...)` calls — offline and online.

## Acceptance tests
- AC1 → `setup` creates the tables in their own schema — hand-run against a real database.
- AC2/AC3 → interrupt in one invocation, resume in a separate one, and the resumed run prints the first run's value — hand-run.
- AC4 → `include_object` excludes the schema, asserted as a pure function; plus an `ast` check that both `configure` calls carry `include_schemas=True` and the shared `include_object`.
- AC5 → `alembic upgrade head` succeeds on a fresh database with the schema present — hand-run.
- AC6 → every automated assertion above runs without building an engine, per `backend/tests/conftest.py`.

## Order
WI1, WI2 and WI4 in parallel; WI3 after WI1. WI2 needs only `schema.py`, which WI1 lands first.

**What the research overturned, and the risks it found:**
1. **The `checkpoints` schema is not configurable.** `langgraph-checkpoint-postgres` 3.1.2 emits unqualified table names and the word `schema` appears nowhere in the package. The only route is the connection's `search_path`, and `setup()` does **not** create the schema — so `CREATE SCHEMA IF NOT EXISTS` must run first. The outcome `model.md:227`-`231` promised holds; the mechanism it names does not. WI4 amends it.
2. **`include_schemas=True` is required**, or the exclusion is incidental rather than deliberate — proved both ways against a live database. It also makes autogenerate reflect every non-system schema; harmless today, revisit when pgvector lands.
3. **The dependency change downgrades `websockets` 17.1 → 16.1.1**, pinned by `langgraph-sdk` and also used by `uvicorn[standard]`. WI1 must smoke-test `make up`, not just the suite.
