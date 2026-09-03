---
phase: 3
step: "3.7"
title: Hybrid retrieval service
summary: RetrievalService fusing PostgreSQL full-text search and pgvector cosine similarity over the existing chunk indexes via RRF in one SQL statement, filtered to approved models, returning provenance-carrying chunks; plus a CLI harness.
effort: 4
dependencies: ["2.18", "2.19"]
---

# Step 3.7 — Hybrid retrieval service

**Effort: 4** — the RRF SQL, the query-embedding wiring, the CLI harness,
and a tuning pass against real data. **No migration** — the tsvector/GIN and
HNSW indexes landed in step 2.18 (`text_tsv`, `ix_chunks_text_tsv`,
`ix_chunks_embedding`); the old step-3.1 migration outline is superseded.

Binding contract: `docs/roadmap/phase-3/shared-knowledge.md` (§Config keys,
§Environment prerequisites). Agent: **backend-dev** (qa reviews the fusion
tests).

## Outline

- `backend/app/services/retrieval_service.py`: `search(session, query_text,
  *, motorbike_ids=None, limit=10) -> list[RetrievedChunk]` — query embedded
  via `get_embeddings()` (2.19 landed contract), then **one SQL statement**:
  two ranked CTEs (FTS over `text_tsv` with
  `plainto_tsquery('english', …)`; cosine distance over `embedding`), each
  capped at `settings.retrieval_candidates_per_leg`, fused by RRF with
  `settings.rrf_k`, joined to `source_documents` + `motorbikes`.
- All filtering inside the SQL, never post-filtering in Python:
  `motorbikes.status = 'approved'`, `embedding IS NOT NULL`,
  `embedding_model = settings.embedding_model`, optional motorbike-id list.
- `RetrievedChunk` (Pydantic): `chunk_id, motorbike_id, text, score,
  source_document_id, source_url, source_title, heading_path, page_number,
  sequence` — the architecture's provenance set exactly.
- Dimension/model-mismatch guard reuses
  `embedding_service.require_matching_dimensions()`; the error names
  `app embeddings rebuild`.
- Config: `RRF_K=60`, `RETRIEVAL_CANDIDATES_PER_LEG=50` (settings, not
  literals — one tuning pass expected).
- `backend/app/cli/retrieval.py`: `app retrieval search "<text>"
  [--bike <ulid>] [--limit]`, registered in `cli/main.py`, printing ranked
  results with scores and provenance.
- Tests: RRF fusion ordering with seeded fake rows, filter clauses asserted
  in the compiled SQL, guard error message.

## Verification

- `docker compose exec app-web app retrieval search "comfortable touring
  bike"` returns ranked chunks with source titles/URLs from an **approved**
  model; `--bike` restricts to that model. *(Needs the approved-models
  prerequisite from shared-knowledge §Environment prerequisites.)*

## Risks / notes

- English-only FTS is deliberate; no language detection.
- "Chunked but unembedded" is a normal state (2.19 landed asymmetry) — the
  non-null-embedding filter is load-bearing, keep it.
