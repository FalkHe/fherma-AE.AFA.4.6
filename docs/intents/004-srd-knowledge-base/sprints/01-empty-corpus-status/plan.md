---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 01 — empty corpus status

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The SRD module shell with its own errors, and a database able to hold citable passages with their vectors: extension, table, cosine HNSW index. `pgvector` declared; README carries the CC-BY attribution. | columns and types match the attachment; index carries `hnsw` + `vector_cosine_ops`; chain head `0002` over `0001`; `downgrade()` reverses | – |
| 2 | backend-python | Asking the corpus what it holds answers with a count and, once ingested, version/model/time; demanding a non-empty corpus fails loudly when it is empty; a configured width disagreeing with the stored column fails before any query. | empty → `SrdCorpusEmptyError`; populated → `None`; status on empty → `rule_count == 0`; mismatch → `SrdVectorWidthError` naming both widths | I1 |
| 3 | backend-python | An operator asks the corpus for its state from the command line, and gets a non-zero exit while it is empty. | empty → exit 1, stderr names 0 rules and the ingest command; populated → exit 0, count/model/time on stdout; mismatch → exit 1, both widths on stderr | I2 |
| 4 | backend-python | An opt-in suite path against a real database, proving the empty report and the guard end to end; the default offline suite untouched. | live: table and index exist after migration, status reports 0 rules and exits 1, guard raises; skips cleanly with no database | I1, I2, I3 |
| qa | qa | Black-box acceptance tests, one per criterion. | below | I2, I3 |

## Interfaces
- **I1** — `backend/app/modules/srd/models.py`: `EMBEDDING_WIDTH = 1536`; `class SrdRule(Base)`, `__tablename__ = "srd_rules"`, columns per `decisions/module-structure.md` §2, `embedding` as `VECTOR(EMBEDDING_WIDTH)`, index `ix_srd_rules_embedding` (`postgresql_using="hnsw"`, ops `vector_cosine_ops`). `backend/alembic/versions/0002_srd_rules.py`: `revision = "0002"`, `down_revision = "0001"`, `upgrade()` opens with `op.execute("CREATE EXTENSION IF NOT EXISTS vector")`. `backend/app/modules/srd/errors.py`: `SrdError(Exception)`, `SrdCorpusEmptyError(SrdError)`, `SrdVectorWidthError(SrdError)`.
- **I2** — `backend/app/modules/srd/service.py`, imported as `from app.modules.srd import service as srd_service`: `def check_vector_width() -> None`, `async def corpus_status(db: AsyncSession) -> CorpusStatus` (calls `check_vector_width()` first), `async def require_corpus(db: AsyncSession) -> None`. `schemas.py`: `CorpusStatus(rule_count: int, source_version: str | None, embedding_model: str | None, ingested_at: datetime | None)`.
- **I3** — `backend/app/modules/srd/commands.py`: `srd_app`, command `status`; wired `cli.add_typer(srd_app, name="srd")` in `backend/app/cli.py`.
- **I4** — `backend/pyproject.toml` gains `markers = ["database: needs a reachable Postgres"]`. `backend/tests/srd/conftest.py` exposes fixture `srd_db`: skips when no server answers, creates a scratch database, pins `DATABASE_URL` + `EMBEDDING_DIMENSIONS=1536` with `get_settings.cache_clear()`, migrates it by subprocess, yields an `AsyncSession`, drops it after. Makefile target `backend-test-db`.

## Acceptance tests (qa)
- AC1 → status on a migrated, never-ingested database names 0 rules and exits 1 (`database`).
- AC2 → the migrated database shows the extension, the attachment's columns, and an HNSW `vector_cosine_ops` index on `embedding` (`database`).
- AC3 → configured width ≠ column width: status exits non-zero naming both, no query attempted (engine-free).
- AC4 → the guard raises on an empty corpus, returns nothing once a row exists (`database`).
- AC5 → with no database reachable, marked tests skip and the rest passes under warnings-as-errors.

## Order
Parallel: WI1, WI4's harness, qa. Then WI2, WI3. Then WI4's live tests.
