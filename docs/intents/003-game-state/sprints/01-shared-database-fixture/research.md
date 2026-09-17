---
author: fhit:architect
owner: agent
created: 2026-09-17
---
# Research: sprint 003/01 — one scratch-database fixture, shared

## Facts

**What `srd_db` does today** (`backend/tests/srd/conftest.py`, one function, `:85`-`:139`):
- reads the admin URL from `os.environ["DATABASE_URL"]`, falling back to `_DEFAULT_ADMIN_URL` (`:53`); `pytest.skip("no reachable Postgres server")` when a 2 s `psycopg.connect` fails (`:77`-`:82`, `:89`-`:90`);
- creates a scratch **database** `srd_test_<16 hex>` over an autocommit admin connection (`:92`-`:96`); `_psycopg_conninfo` strips the `+psycopg` driver tag (`:60`), `_with_database` swaps only the URL path (`:70`);
- pins `DATABASE_URL` to the scratch URL and `EMBEDDING_DIMENSIONS` to `"1536"` (`:100`-`:101`, constant `:57`), then `get_settings.cache_clear()` (`:102`);
- runs `alembic upgrade head` as a **subprocess** in `BACKEND_ROOT = parents[2]` (`:47`, `:107`-`:117`), `pytest.fail`ing with both streams on a non-zero exit. In-process is impossible: `backend/alembic/env.py:23` calls `fileConfig()`, which reconfigures logging under the autouse structlog guard (`backend/tests/conftest.py:40`-`:60`); `env.py:26` reads the URL from `get_settings()` at run time, so the subprocess picks up the pin through the inherited environment;
- yields an `AsyncSession` from its **own** `create_async_engine` (`:119`-`:121`), never the app's cached `get_engine()`/`get_sessionmaker()`;
- teardown (`:122`-`:139`): `asyncio.run(session.close())`, `engine.dispose()`, restore both env vars to their prior value or pop them if absent, `cache_clear()` again, then `DROP DATABASE IF EXISTS … WITH (FORCE)`.

**Suite-wide stubbing and how a `database` test escapes it.** `backend/tests/conftest.py:18`-`:26` pins env vars *before* `app` is imported, including `EMBEDDING_DIMENSIONS="4"` (`:25`), and `:34` clears the settings cache. The DB stub is not global: it is bound in the `app` fixture only (`:69`, `:83`). A `database` test escapes simply by requesting none of `app`/`client` and taking the scratch fixture instead, which re-pins the same env vars and builds its own engine. The marker itself changes nothing at run time.

**Marker and target.** `markers = ["database: needs a reachable Postgres"]` and `addopts = "-q"` — no deselection — in `backend/pyproject.toml:63`-`:64`; `filterwarnings = ["error"]` at `:62`. `make backend-test` is `--no-deps` (`Makefile:10`, `:60`-`:61`) so nothing answers and the fixture skips; `make backend-test-db` starts postgres and runs `pytest -m database` (`Makefile:64`-`:67`). Skipping is therefore *reachability*-based, not marker-based.

**Renaming `srd_test_<hex>` → `test_<hex>` breaks nothing in the repo.** The only references to the old prefix are the fixture and its docstring (`:9`, `:92`); no test asserts a database name (`backend/tests/srd/test_database_harness.py:20`-`:33` asserts extension + table; `backend/tests/srd/test_acceptance_empty_corpus_status.py:44`, `:58`, `:134` assert columns, index and service behaviour), and no Makefile target, compose file or doc greps for it. `docs/architecture.md:43` already describes the arrangement generically, so no doc change falls due here.

**Two consumers, five fixture users.** `srd_db` is used by the four `database`-marked tests above. `backend/app/modules/playthrough/` does not exist yet, so the new test can only assert through SQL — `srd_rules` present proves the whole chain ran. `backend/tests/__init__.py` exists and sibling tests already import `from tests.factories import …` (`backend/tests/auth/test_register.py:21`), so `from tests.database import scratch_db` resolves the same way; `tests/database.py` is not collected (no `test_` prefix).

## Work items

- **WI1 — `backend/tests/database.py`**: the helper below, lifted from the SRD fixture with the four private helpers, `test_<hex>` naming and `BACKEND_ROOT = Path(__file__).resolve().parents[1]` (**one level up from today's `parents[2]`** — the file moves one directory up). No pytest fixture in this file.
- **WI2 — `backend/tests/srd/conftest.py`**: collapses to the `srd_db` fixture over WI1 with the `1536` pin; the `vector`/`1536` knowledge stays in `tests/srd/`. Needs WI1's signature only.
- **WI3 — `backend/tests/playthrough/`**: `__init__.py`, `conftest.py` with `playthrough_db` (no pins), and one `@pytest.mark.database` test asserting `srd_rules` exists in `information_schema.tables` via `asyncio.run(...)` (no `pytest-asyncio` in this suite). Needs WI1's signature only.

WI2 and WI3 are independent of each other and can run in parallel once the interface below is fixed; both are verified against WI1's landed file by `make backend-test`, `make backend-test-db` and `make lint` (AC3).

## Interfaces

```python
# backend/tests/database.py
def scratch_db(**env_pins: str) -> Iterator[AsyncSession]:
```

A plain generator, not a fixture. Semantics, in order: skip when unreachable → create `test_<uuid4().hex[:16]>` → set `DATABASE_URL` to the scratch URL **and** every `env_pins` key to its value → `get_settings.cache_clear()` → subprocess `alembic upgrade head` (`pytest.fail` on non-zero, both streams in the message) → yield an `AsyncSession` on its own engine → in `finally`: close, dispose, restore `DATABASE_URL` and every pinned key to its prior value (pop where it was absent), `cache_clear()`, `DROP DATABASE IF EXISTS "<name>" WITH (FORCE)`. Pin values are strings, passed through untouched; keys are environment-variable names.

Both fixtures are one delegation each:

```python
@pytest.fixture
def srd_db():
    yield from scratch_db(EMBEDDING_DIMENSIONS="1536")   # tests/srd/conftest.py

@pytest.fixture
def playthrough_db():
    yield from scratch_db()                              # tests/playthrough/conftest.py
```

## Open questions

- Technical, does not block: "skipped under `make backend-test`" holds because `--no-deps` leaves no reachable server — but if a developer's dev stack is up, the container joins its network and the `database` tests *run* (and pass) instead of skipping. AC3 forbids redefining the target, so this sprint keeps the behaviour as is.
- None product-visible.
