---
phase: 3
step: "3.9"
title: RAG pipeline service
summary: The advanced-RAG pipeline — translate the utterance, resolve filters and named bikes to candidates, fan the rewritten queries through hybrid retrieval, fuse with a second RRF pass, and degrade gracefully; with an app rag ask CLI harness.
effort: 3
dependencies: ["3.7", "3.8"]
---

# Step 3.9 — RAG pipeline service

**Effort: 3** — orchestration over two finished services plus the fallback
path and CLI; no new SQL, no new schema.

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md`. Agent:
**backend-dev**.

## Outline

- `backend/app/services/rag_pipeline_service.py`: `retrieve(session,
  utterance, *, preferences=(), history_summary="", limit=10) -> RagResult`
  — call the 3.8 translation (low temperature), resolve `spec_filters` via
  `catalogue_search_service.find_motorbike_ids` and
  `target_motorbike_names` via name resolution to a candidate-id list, fan
  `search_queries` through `retrieval_service.search` scoped to the
  candidates (or unscoped when no filters derived), fuse the per-query
  rankings with a second RRF pass (same `rrf_k`), dedupe chunks by id.
- **Fallback path (pinned):** translation failure or nothing usable →
  retrieve with the raw utterance and no filters — the pipeline degrades,
  never raises (the 2.10/2.12/2.17 typed-failure convention).
- `RagResult` carries `queries`, `applied_filters`,
  `candidate_motorbike_ids`, `chunks` — the "why these sources" payload the
  agent turns into `sources` and Langfuse will trace in Phase 5.
- `backend/app/cli/rag.py`: `app rag ask "<utterance>"` printing translated
  queries, applied filters, candidate bikes, and fused chunks with
  provenance; registered in `cli/main.py`.
- Tests: cross-query fusion + dedup ordering, candidate scoping, fallback on
  malformed LLM output (mocked model).

## Verification

- `docker compose exec app-web app rag ask "I'm 1.65m, just got my A2,
  mostly city commuting"` shows an A2/seat-height filter being derived, a
  candidate shortlist, and prose chunks only from those bikes, each with
  provenance. **This closes milestone M3's backend half.**

## Risks / notes

- The pipeline is consumed exactly once — as the 3.13
  `retrieve_bike_knowledge` tool. Don't wire it into the responder job
  directly.
