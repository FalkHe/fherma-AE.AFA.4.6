---
phase: 5
step: "5.6"
title: LLM client timeouts & transient-error mapping
summary: Explicit timeout/max_retries constants on both LLM client factories, and the OpenAI SDK timeout/connection errors join the chat job's transient set — closing the step-3.9 stalled-embeddings finding through the single global retry budget.
effort: 2
dependencies: []
---

# Step 5.6 — LLM client timeouts & transient-error mapping

**Effort: 2** — two factory signatures, one tuple extension, tests; the
policy is fully pinned (shared-knowledge D3).

Binding contract: `docs/roadmap/stage-01/phase-5/shared-knowledge.md` (D3). Prior
pins: `TransientJobError` is the only retried exception
(`backend/app/jobs/broker.py` SmartRetryMiddleware — do not add a second
retry mechanism); the apology path in `backend/app/jobs/chat.py` (Phase-3
landed decision 3.5 — ids-after-rollback rule). Agent: **backend-dev**.
Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up for the live check; **restart `app-worker` after
landing** (job-executed code — the 2b.4 pin).

## Outline

- `backend/app/llm/models.py`: `CHAT_REQUEST_TIMEOUT_SECONDS = 60`,
  `LLM_MAX_RETRIES = 2` module constants; pass `timeout=`/`max_retries=` to
  `ChatOpenRouter`. **No new config keys** — constants, not settings.
- `backend/app/llm/embeddings.py`: `EMBEDDINGS_REQUEST_TIMEOUT_SECONDS = 30`,
  reuse `LLM_MAX_RETRIES`; pass to `OpenAIEmbeddings`. This closes the 3.9
  open finding (a stalled embeddings call hung ~600 s on the SDK default).
- `backend/app/jobs/chat.py`: add the OpenAI SDK's timeout/connection
  exception types (e.g. `openai.APITimeoutError`, `openai.APIConnectionError`
  — verify exact names against the installed SDK) to
  `TRANSIENT_GATEWAY_ERRORS`, so client-timeout failures retry through the
  existing SmartRetryMiddleware budget (3 attempts, exponential) and then
  take the apology path. Anything non-transient keeps failing immediately.
- Sanity-check the interaction: 2 SDK-internal retries × 60 s must stay
  comfortably inside `AGENT_TIMEOUT_SECONDS` (120) for a single call — the
  asyncio timeout still bounds the whole turn; if the arithmetic looks
  wrong, stop and report rather than tuning constants ad hoc.
- Tests: `backend/tests/llm/test_models.py` asserts the constructor kwargs
  (both factories); job tests assert the extended transient tuple maps to
  `TransientJobError`.

## Verification

- Suite + lint green.
- Live: with a blackholed upstream (e.g. `OPENROUTER_API_KEY` valid but
  base-url pointed at a non-routable host in a scratch env var — or simply
  an invalid key for the fast path) a chat turn reaches the apologetic
  message + `failed` operation within the timeout budget, never a 600 s hang.
- `docker compose restart app-worker` done.

## Risks / notes

- Do not touch `rag_pipeline_service`/`retrieval_service` degradation rules —
  `MissingApiKeyError`/`StaleEmbeddingsError` propagation stays as pinned in
  Phase 3.
- 5.9 edits the same file (`llm/models.py`) — land this first (in-track
  order) or coordinate.
- Append cross-step decisions (`### Step 5.6`) to `shared-knowledge.md`,
  naming the exact SDK exception types added — 5.17's dead-LLM scenario
  proves this behaviour.
