---
author: sprint
owner: agent
created: 2026-09-22
---
# Research: sprint 004-03 — corpus ingested (port from the stale branch)

## Facts
- `origin/sprint/004-03-corpus-ingested` (2026-09-16) holds a working `service.ingest` written against the old sprint 02; it uses only names that exist identically on `main` today: `fetch_source`, `chunk_source`, `check_vector_width`, `SrdRule`, `SOURCE_VERSION`, `SOURCE_FILENAME`, `SRD_ROOT`, `get_settings().embedding_model`, `llm_service.embed_texts(texts, model=) -> EmbeddingResult` (`.vectors`, `.usage.cost_usd`).
- Its shape: `check_vector_width()` → remember previous stored bytes → `fetch_source` → `chunk_source` → embed in `EMBED_BATCH_SIZE = 256` batches, summing cost with a `cost_complete` flag → one short transaction `delete(SrdRule)` + `add_all` + `commit`, rollback on failure → on any `BaseException` after the fetch restore the previous stored file bytes → return `IngestReport(source_version, source_bytes, chunk_count, token_count, cost_usd, cost_complete)`. This already satisfies sprint 04's wholesale-replace core.
- It also adds `UniqueConstraint("source_version", "heading_path", "ordinal")` on `SrdRule` with a migration numbered `0003`; `main` already has `0003`–`0008`, so the port renumbers it to `0009` (revises `0008`).
- A mechanical rebase is impossible: 22 add/add conflicts, and the old branch has sprint 04 merged into it. Porting by hand is the least effort.
- Old tests (`test_ingest_service.py`, ~500 lines) are written against the old conftest; only a few behaviours need re-creating here.
- `main`'s `commands.py` has `ingest --dry-run`; without the flag it currently exits 1 saying sprint 03 will land it. `srd status` prints rules / embedding model / ingested at.
- Live proof needs Postgres up (`docker compose up -d postgres`), `alembic upgrade head`, and a real `OPENROUTER_API_KEY` in `.env`; 508 k tokens at text-embedding-3-small costs about one cent.

## Work items
WI1 (backend-python): port `ingest` + `IngestReport` + unique constraint + migration `0009`, wire the real `app srd ingest`, minimal tests, live run.

## Open questions
None product-visible.
