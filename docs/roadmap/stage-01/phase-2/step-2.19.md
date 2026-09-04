---
phase: 2
step: "2.19"
title: Embeddings & re-embed CLI
summary: The OpenRouter embeddings client (model + dimensions recorded per chunk, batched), chunk+embed as the final ingestion stage, and `app embeddings rebuild` enqueuing an operation-tracked Taskiq job — with loud failure on dimension mismatch.
effort: 4
dependencies: ["2.14", "2.16", "2.18"]
agent: backend-dev
track: backend
---

# Step 2.19 — Embeddings & re-embed CLI

**Effort: 4** — embeddings client + ingestion stage + the rebuild job with
model-change handling. Closes the backend track.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *Chunking & embedding
decisions* (batching, per-row model/dimensions, the **loud-failure
dimension guard**), *LLM decisions* (OpenRouter-only; the 2.16 landed
decision records the embeddings smoke result — read it), *Taskiq wiring*,
*Operation lifecycle* (embeddings = the 90 % milestone). Zero deviations;
stop and report if one seems necessary — especially if OpenRouter's
embeddings route fails.

## Files

- Create `backend/app/llm/embeddings.py` (`get_embeddings()`)
- Create `backend/app/services/embedding_service.py`
- Create `backend/app/jobs/embeddings.py` (`embeddings.rebuild` task)
- Create `backend/app/cli/embeddings.py` (`rebuild` command)
- Create mocked tests under `backend/tests/`
- Modify `backend/app/jobs/ingestion.py` (chunk+embed stage at 90 %),
  `compose.yaml` (worker modules + `app.jobs.embeddings`),
  `backend/app/core/config.py`, `.env.dist` (`EMBEDDING_MODEL`,
  `EMBEDDING_DIMENSIONS`), `backend/app/cli/main.py`

## Implementation outline

- `llm/embeddings.py` per the pinned wiring (shared-knowledge → *LLM
  decisions*): `langchain_openai.OpenAIEmbeddings` against
  `https://openrouter.ai/api/v1` with `check_embedding_ctx_length=False`
  (mandatory — LangChain issue #35204); dependency `langchain-openai` added
  here. HTTPX fallback to the same OpenRouter endpoint only if the wrapper
  misbehaves on the pinned versions — record it if taken.
- `embedding_service`: batch 64 texts/request; assert
  `len(vector) == settings.embedding_dimensions` before writing; write
  `embedding`, `embedding_model`, `embedding_dimensions` per chunk row.
- Guard (startup of the rebuild + ingestion stage): configured
  `EMBEDDING_DIMENSIONS` ≠ `vector` column dimension → fail loudly naming
  the required migration path; never truncate silently.
- Ingestion stage: chunk (2.18) + embed the bike's documents before
  `in_review` — embedding errors here are **transient-retry then warning**
  (review can proceed; `app embeddings rebuild` backfills).
- `app embeddings rebuild`: enqueues `embeddings.rebuild` — re-chunks and
  re-embeds everything with the configured model, tracked as an operation
  (progress = documents processed), rewrites rows on model change.

## Verification

- `make backend-test` green (mocked embeddings: batching, per-row metadata,
  dimension-guard failure).
- Manual: fresh ingest → chunks with non-null embeddings and correct model
  string; `app embeddings rebuild` → operation succeeds, zero NULL
  embeddings; setting a wrong-dimension model fails loudly citing the
  migration path.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
