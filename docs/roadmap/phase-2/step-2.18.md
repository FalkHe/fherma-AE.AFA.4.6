---
phase: 2
step: "2.18"
title: Chunks table & chunking
summary: The chunks table + migration (provenance columns, nullable vector(1536), generated English tsvector + GIN, HNSW cosine index) and the heading-aware structural chunker, with a synchronous `app chunks rebuild` CLI.
effort: 3
dependencies: ["2.1", "2.6"]
agent: backend-dev
track: backend
---

# Step 2.18 — Chunks table & chunking

**Effort: 3** — one table, one deliberate chunker, one CLI. Retrieval logic
stays in Phase 3; this step lands the data. **Phase-3 note: 3.1's
"migration adds tsvector + GIN + HNSW" is superseded — they land here.**

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *DB schema → chunks* (column
by column, incl. the generated tsvector and HNSW parameters) and *Chunking &
embedding decisions* (splitter chain, sizes). Zero deviations; stop and
report if one seems necessary.

**Migration-order rule:** lands after 2.6's migration (single Alembic head).

## Files

- Create `backend/app/db/models/chunk.py` + one Alembic version
- Create `backend/app/services/chunking.py`
- Create `backend/app/cli/chunks.py` (`rebuild [slug]`, synchronous)
- Create chunker tests under `backend/tests/services/`
- Modify `backend/app/db/models/__init__.py`,
  `backend/app/core/config.py`, `.env.dist` (`CHUNK_SIZE_CHARS`,
  `CHUNK_OVERLAP_CHARS`), `backend/pyproject.toml` + `uv.lock` (`pgvector`,
  `langchain-text-splitters`), `backend/app/cli/main.py`

## Implementation outline

- Migration exactly per the pinned schema: nullable `vector(1536)`,
  generated stored `text_tsv` + GIN, HNSW cosine (m=16, ef_construction=64),
  unique (source_document_id, sequence).
- `chunking.py`: `MarkdownHeaderTextSplitter` →
  `RecursiveCharacterTextSplitter` at the pinned sizes; `heading_path` from
  the header split; provenance + denormalized `motorbike_id` on every row.
  Structural only — no semantic/LLM chunking.
- Re-chunk semantics: rebuild deletes and rewrites a document's chunks
  (embeddings reset to null — 2.19 fills them).
- `app chunks rebuild [slug]`: chunk all (or one bike's) documents,
  synchronous (fast, no job needed at this stage).
- Run `make build` after the dependency change.

## Verification

- `make backend-test` green (chunker: heading paths, overlap, oversize
  splits); migration round-trips.
- Manual: after an ingest, `app chunks rebuild suzuki-gsr-600` → psql shows
  chunks with `heading_path`, `sequence`, populated `text_tsv`, NULL
  embeddings.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
