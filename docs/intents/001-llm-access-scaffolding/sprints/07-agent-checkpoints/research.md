---
author: fhit:architect
owner: agent
created: 2026-09-16
---
# Research: sprint 07 — an agent's state survives between two runs

Every fact below was **run**, not read: postgres was started, probed from throwaway containers, then stopped. `langgraph`
1.2.11 · `langgraph-checkpoint-postgres` 3.1.2 · `alembic` 1.19.2 — local package + live run.

## Facts

**The ruling holds; its mechanism does not.** `docs/general/model.md:227`-`231` still promises a dedicated `checkpoints`
schema — but **the schema is not configurable**. The DDL at `site-packages/langgraph/checkpoint/postgres/base.py:42`-`90`
creates *unqualified* `checkpoint_migrations`, `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, and the string
`schema` occurs nowhere in the package. The only lever is the connection's **`search_path`**: verified, with
`?options=-csearch_path%3Dcheckpoints` all four tables land in `checkpoints` (`checkpoints.checkpoints` included —
legal). The promised outcome is reachable; the implied route is not. `setup()` does **not** create the schema —
`CREATE SCHEMA IF NOT EXISTS` must precede it — and is a verified no-op on a second run.

**Connection string.** `from_conn_string` (`.../postgres/aio.py:64`-`87`) is an **async context manager**, not an
awaitable, and connects `autocommit=True` — which is why the `CREATE INDEX CONCURRENTLY` migrations (`base.py:82`-`88`)
succeed. It takes a **libpq conninfo string**; `DATABASE_URL` is `postgresql+psycopg://…` (`backend/tests/conftest.py:20`,
`.env.dist:15`) and passed unchanged fails loudly — `psycopg.ProgrammingError: missing "=" after …` (verified). The
`+psycopg` tag must be stripped.

**Alembic.** `backend/alembic/env.py:44` configures without `include_schemas`, so autogenerate reflects the default schema
only and ignores `checkpoints` **incidentally** — what AC4 forbids. Verified live: flip `include_schemas=True` alone and
autogenerate proposes dropping `checkpoints.checkpoints`, `checkpoints.checkpoint_blobs` and their index; add an
`include_object` rejecting `object.schema == "checkpoints"` and the revision is empty again. **The exclusion is explicit
and load-bearing only if `include_schemas=True` ships with it.** AC5 verified separately. Ordering is free: Alembic owns
`public`, the checkpointer `checkpoints`, neither reads the other's tables. But **`env.py` cannot be imported by a test**
— it runs `run_migrations_online()` at module scope (`:70`-`73`) and builds a real engine (`:52`-`56`), both forbidden by
`backend/tests/conftest.py:3`-`10`. So the predicate lives in an importable `app.core.*` module, *wired* from `env.py`.

**Dependencies.** Neither package is declared (`backend/pyproject.toml:6`-`19`); `uv lock` against the real manifest
resolves cleanly (+`langgraph-checkpoint` 4.2.0, `-prebuilt` 1.1.0, `-sdk` 0.4.4, `ormsgpack`) but **downgrades
`websockets` 17.1 → 16.1.1**, pinned by `langgraph-sdk` and also used by `uvicorn[standard]` — smoke-test `make up`.
`anyio<4.15` (`:46`) is unaffected, `psycopg[binary,pool]` (`:12`) is the only driver needed, and every import is clean
under `-W error`, so `filterwarnings=["error"]` is safe.

**Interrupt/resume.** `langgraph.types.interrupt(value)` and `Command(*, resume=…)` (signatures verified). Proven across
**two separate OS processes** on one `thread_id`: run 1 returned `__interrupt__` with `next=('two',)`; run 2, invoked with
`Command(resume="RESUMED-VALUE")`, returned `answer='hello-from-run-1|RESUMED-VALUE'` — run 1's value, read back out of
postgres. `make backend-test` runs `--no-deps` (`Makefile:10`), so the suite never has a database: this round trip stays a
hand-run live check, as in sprints 01/04/05.

## Work items

- **WI1 seam**: pin the two packages, `uv lock`, `make build`; add `app/core/checkpointer/schema.py` (constant +
  `include_object`, zero third-party imports) and `service.py`. Tests: conn-string derivation, a pure function.
- **WI2 Alembic exclusion**: wire `include_schemas=True` + `include_object` into both `context.configure` calls in
  `backend/alembic/env.py`. Tests (AC6, no engine): call `include_object` directly with fabricated arguments, plus an
  `ast` parse of `env.py` asserting both calls carry both keywords and that `include_object` comes from `schema.py`.
- **WI3 CLI + demo graph**: `app/core/checkpointer/demo_graph.py` (throwaway — the docstring says so, phase 7 deletes it)
  and `commands.py` with `setup` / `demo start` / `demo resume`; register in `app/cli.py`. Tests: `CliRunner` with the
  service monkeypatched — no database, no graph execution.

WI1 and WI2 run in parallel once `schema.py` exists (WI2 needs nothing else from WI1); WI3 follows WI1.

## Interfaces

`app/core/checkpointer/schema.py` — no third-party imports, so `env.py` and its test stay engine-free:
```python
CHECKPOINTER_SCHEMA = "checkpoints"
def include_object(object, name, type_, reflected, compare_to) -> bool:
    return getattr(object, "schema", None) != CHECKPOINTER_SCHEMA
```
`app/core/checkpointer/service.py`:
```python
def checkpointer_conn_string(database_url: str) -> str          # strips "+<driver>", adds the options param
def checkpointer() -> AsyncContextManager[AsyncPostgresSaver]   # from_conn_string(...) passthrough
async def ensure_schema() -> None   # CREATE SCHEMA IF NOT EXISTS checkpoints
async def setup() -> None           # ensure_schema(), then `await saver.setup()`
```
Pinned by test, exactly — build it with `urllib.parse`; the `%3D` escaping the inner `=` is required:
`checkpointer_conn_string("postgresql+psycopg://app:app@postgres:5432/application")` ==
`"postgresql://app:app@postgres:5432/application?options=-csearch_path%3Dcheckpoints"`

`env.py`: `from app.core.checkpointer.schema import include_object`, passed with `include_schemas=True` to **both**
`context.configure(...)` calls (offline `:32`, online `:44`).

CLI `app checkpoint …`, stdout only, exit 0 / 1: `setup` → `checkpoints schema ready`; `demo start --thread <id>` →
`interrupted: <json>`; `demo resume --thread <id> --value <text>` → `answer: <left>|<value>` — that line is AC3.

Live check (AC1-AC3, by hand; postgres first — `app-cli` has no `depends_on`):
```
docker compose up -d postgres
docker compose run --rm app-cli app checkpoint setup
docker compose run --rm app-cli app checkpoint demo start --thread demo-1
docker compose run --rm app-cli app checkpoint demo resume --thread demo-1 --value hello
```

## Open questions

- *technical, human ruling* — `model.md:227`-`231` implies a schema option that does not exist. Amend it to name
  `search_path` as the mechanism, or leave a known inaccuracy standing?
- *technical* — `include_schemas=True` makes autogenerate reflect **every** non-system schema (harmless today; revisit
  when pgvector lands). And: should `checkpoint setup` join `alembic upgrade head` in `entrypoint-web.sh` for phase 7?
- No product-visible questions: nothing in this sprint reaches a user.
