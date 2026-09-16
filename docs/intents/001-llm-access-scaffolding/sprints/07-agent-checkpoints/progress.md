---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: done
---
# Progress: Sprint 07

| WI | Status | Note |
|---|---|---|
| 1 | done | langgraph 1.2.11 + checkpoint-postgres 3.1.2, make up verified, 8 tests |
| 2 | done | env.py both configure calls, ast-checked, 6 tests, proven red |
| 3 | done | CLI + demo graph, 6 tests; found the setup() blocker by hand-run |
| 4 | done | model.md names search_path, not a schema option |

Status: `open | running | done | failed`

## Issues
- Only sprint of this intent needing a real database. AC1/AC2/AC3/AC5 are hand-run; AC4/AC6 are the automated part and must stay engine-free.
- Research asked for a human ruling on `model.md:227`-`231`. Judged a documentation-accuracy matter, not product-visible: the doc names a schema mechanism that does not exist, and standing inaccuracies in these docs have already misled three sprints. WI4 amends it.
- Research left a dev database volume `fherma-aeafa46_postgres-data` that it created (removal was denied by the permission system). Left in place deliberately — this sprint needs a database for its hand-run checks, and deleting a database volume unprompted is not reversible.

- **A blocker the suite structurally could not catch.** `ensure_schema()` used `async with psycopg.AsyncConnection.connect(...)` without awaiting the coroutine, so `app checkpoint setup` raised `TypeError`. Every test monkeypatches the database away (conftest forbids a real engine), so nothing exercised the line; WI3 found it only by hand-running the CLI. Fixed, and covered by tests whose fakes are coroutine functions — a plain-function stub would not have caught it.
- Lead verified all six ACs live: dropped the schema, `setup` recreated all four tables **in `checkpoints`**; a uuid4 seed from process 1 reappeared in a separate container's process 2 (AC2/AC3); `alembic upgrade head` succeeded with the schema present (AC5); and `alembic revision --autogenerate` produced `pass`/`pass` with the tables physically there (AC4). Probe revision removed.

## Backlog proposals
- Should `checkpoint setup` join `alembic upgrade head` in `entrypoint-web.sh` for phase 7? Out of scope here.

## Verify
Round 1: **changes-requested** (note #101). All six ACs passed live, but `docs/architecture.md:15` and `docs/general/backend-stack.md:14` still said LangGraph was not wired, which this sprint falsified. Non-blocking: `demo resume` on an unstarted thread printed a bare `KeyError`.
AC4 proven load-bearing both ways: dropping `include_object` makes autogenerate emit four `drop_table`s; dropping `include_schemas=True` reddens the `ast` test naming `do_run_migrations`.
Round 2: **approved** (note #102). Docs corrected and re-read in full for newly introduced inaccuracies; the `resume` guard verified not to mask real failures — a started thread whose node raises still surfaces its own `ValueError`. 510 passed.
Approval withheld on the platform throughout — author and reviewer are the same account.
