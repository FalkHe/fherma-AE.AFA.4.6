---
author: fhit:architect
owner: agent
created: 2026-09-16
---
# Research: sprint 004-01 — empty corpus status

## Facts

**Intent 001 backlog 04 has landed — do not re-declare.** `Settings.embedding_model`
(`backend/app/core/settings.py:20`) and `embedding_dimensions: int = Field(default=1536, ge=1)`
(`:21`) exist; `embed_texts(texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult`
exists at `backend/app/core/llm/service.py:295`, with `EmbeddingResult(vectors, usage)` (`:78`).
`_vectors_from_response` (`:246`) already raises `LlmConfigurationError` when a *returned vector's*
width differs from `settings.embedding_dimensions` (`:285`-`:288`) — that is the provider-side
check, **not** AC3's column-width check, which nothing covers yet.

**Migration chain.** Head is `revision: str = "0001"`, `down_revision = None`
(`backend/alembic/versions/0001_baseline.py:18`-`:19`) — the only revision. `env.py` takes one
import line per module (`backend/alembic/env.py:12`-`:14`) and overrides the URL from settings at
run time (`:25`), so pointing Alembic elsewhere means changing `DATABASE_URL` + `get_settings.cache_clear()`,
not the Alembic `Config`. `file_template = %%(rev)s_%%(slug)s` (`backend/alembic.ini:4`).
Constraint names come from `NAMING_CONVENTION` (`backend/app/core/db.py:19`-`:25`); `ix` →
`ix_%(table_name)s_%(column_0_name)s`. `ID_TYPE = CHAR(26)` and `generate_id() -> str`
(`backend/app/core/ids.py:12`-`:17`); `0001_baseline.py:15` restates `ID_TYPE = sa.CHAR(26)` locally.

**Dependency.** `pgvector` is **not** in `backend/uv.lock` (nor `tiktoken`, `pytest-asyncio`).
`pgvector` 0.5.0 — PyPI, requires-python `>=3.10`; `from pgvector.sqlalchemy import VECTOR`
(`Vector` is an alias), HNSW via `Index(..., postgresql_using='hnsw', postgresql_ops={'embedding':
'vector_cosine_ops'})`, extension via plain `CREATE EXTENSION IF NOT EXISTS vector` — context7
`/pgvector/pgvector-python`. Postgres is `pgvector/pgvector:pg16` (`compose.yaml:76`); the extension
is available but **not created** in any database yet. SQLAlchemy 2.0.52, Alembic 1.19.2, Typer 0.27.2,
pytest 9.1.1 (`backend/uv.lock`).

**CLI.** Groups are registered by one line each in `backend/app/cli.py:29`-`:32`. Failure precedent:
message to **stderr**, `raise typer.Exit(code=1)` (`backend/app/modules/content/commands.py:16`-`:17`,
`backend/app/core/llm/commands.py:37`-`:52`). Async work from a Typer command runs through
`asyncio.run(...)` (`backend/app/core/checkpointer/commands.py:42`). **There is no error-envelope or
domain-code convention for the CLI** — `ErrorCode` (`backend/app/core/errors.py:17`-`:34`) is HTTP-only;
CLI contract is "one line, right stream, exit code".

**Tests.** `pyproject.toml:59`-`62`: `testpaths=["tests"]`, `filterwarnings = ["error"]`,
`addopts = "-q"`, **no `markers` section** — an undeclared marker raises `PytestUnknownMarkWarning`,
which is therefore fatal. `backend/tests/conftest.py:1`-`14` binds the suite to "never constructs a
real database engine", fully synchronous, no `pytest-asyncio`; `get_db_session` is overridden with
`object()` (`:69`-`:74`). Env vars are pinned before `app` is imported (`:18`-`:26`) — including
**`EMBEDDING_DIMENSIONS = "4"`** (`:25`), depended on by `tests/core/llm/test_embeddings.py:18`.
`Makefile:10` runs the suite with `--no-deps`, and `app-cli` has no `depends_on` (`compose.yaml:48`-`:60`),
so **no Postgres is running during `make backend-test`**. Precedent for an untestable live seam:
fakes plus a documented manual live check (`backend/tests/core/checkpointer/test_service.py:1`-`15`).

## Work items

- **WI1 table**: `modules/srd/` scaffold (`__init__.py`, `README.md` incl. CC-BY, `errors.py`),
  `models.py` with `SrdRule`, revision `0002`, the `env.py` line, `pgvector` added to
  `pyproject.toml` + lock. Tests (engine-free): column set and types, index name and dialect kwargs,
  chain head is `0002` over `0001`, `downgrade()` reverses.
- **WI2 service**: `schemas.py` `CorpusStatus`, `service.corpus_status` / `require_corpus` /
  `check_vector_width`. Tests: empty → `SrdCorpusEmptyError`; rows → returns `None`; mismatch →
  `SrdVectorWidthError` naming both widths; match → silent.
- **WI3 command**: `commands.py` `srd_app` with `status`, registered in `cli.py`. Tests (service
  faked, `CliRunner`): empty → exit 1, stderr line naming 0 rules; populated → exit 0, counts on
  stdout; mismatch → exit 1, stderr names both widths.
- **WI4 real-database test path**: `tests/srd/conftest.py` opt-in fixture, the `database` marker
  declared in `pyproject.toml`, a Makefile target, and the tests proving AC1/AC2/AC4 live.

WI1 and WI4's harness run in parallel; WI2 and WI3 then run in parallel against the interfaces below.

## Interfaces

**WI1 → WI2/WI4** — `backend/app/modules/srd/models.py`:
`EMBEDDING_WIDTH = 1536`; `class SrdRule(Base)`, `__tablename__ = "srd_rules"`, columns per
`decisions/module-structure.md` §2, `embedding` as `VECTOR(EMBEDDING_WIDTH)`, index named
`ix_srd_rules_embedding` (matches `NAMING_CONVENTION`). Revision id `"0002"`, file
`alembic/versions/0002_srd_rules.py`, `down_revision = "0001"`, `upgrade()` starting with
`op.execute("CREATE EXTENSION IF NOT EXISTS vector")`. `errors.py`: `SrdError(Exception)`,
`SrdCorpusEmptyError(SrdError)`, `SrdVectorWidthError(SrdError)`.

**WI2 → WI3/WI4** — `backend/app/modules/srd/service.py`, called as
`from app.modules.srd import service as srd_service`:
`def check_vector_width() -> None`, `async def corpus_status(db: AsyncSession) -> CorpusStatus`
(calls `check_vector_width()` first), `async def require_corpus(db: AsyncSession) -> None`.
`CorpusStatus(rule_count: int, source_version: str | None, embedding_model: str | None,
ingested_at: datetime | None)`.

**WI3 → WI4** — `backend/app/modules/srd/commands.py`: `srd_app`, command name `status`; wired
`cli.add_typer(srd_app, name="srd")` in `app/cli.py`.

**WI4 → the suite** — `pyproject.toml` gains
`markers = ["database: needs a reachable Postgres"]`; `tests/srd/conftest.py` exposes fixture
`srd_db` which skips when no server answers, creates a scratch database, sets `DATABASE_URL` to it
plus `EMBEDDING_DIMENSIONS=1536` and calls `get_settings.cache_clear()`, runs `alembic upgrade head`
**as a subprocess** (so `env.py`'s `fileConfig` cannot re-configure the test process's logging),
yields an `AsyncSession` from its own `create_async_engine`, and drops the scratch database.
Tests stay synchronous and wrap service calls in `asyncio.run(...)`. Makefile:
`$(COMPOSE) up -d postgres` then `$(COMPOSE) run --rm app-cli pytest -m database`.

## Open questions

*product-visible*
- **Does the empty-corpus line tell the operator what to do next** — bare "0 rules", or naming the
  ingest command? It is the only thing this sprint's user sees.
- **An un-migrated database**: `app srd status` would surface a raw Postgres "relation does not
  exist". Say "not migrated" instead, or leave it?

*technical (agent's call unless vetoed)*
- `SrdVectorWidthError` is **not** in the approved `decisions/module-structure.md` §3 — added because
  AC3 needs a distinguishable failure. The alternative is a bare `SrdError`.
- Conftest's global `EMBEDDING_DIMENSIONS=4` is overridden **per fixture**, never globally:
  raising the global pin to 1536 would break `tests/core/llm/test_embeddings.py`.
- Scratch **database** over scratch schema: `CREATE EXTENSION` is per-database, and the dev
  `application` database must not gain `srd_rules` rows from a test run.
- `make backend-test` keeps `--no-deps`; the marked tests skip there by design (AC5's "still pass").
- Residual risk: `filterwarnings=["error"]` means any warning from a first real psycopg/SQLAlchemy
  connection fails the suite. Unknown until WI4 runs.
