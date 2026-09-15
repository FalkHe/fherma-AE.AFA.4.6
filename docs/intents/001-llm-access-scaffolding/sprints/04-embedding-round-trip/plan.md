---
author: sprint
owner: agent
created: 2026-09-15
---
# Plan: Sprint 04 — an embedding call round-trips and reports what it cost

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Config carries the embedding model and its vector width | both defaults match `.env.dist`; a width of 0 is rejected; the suite pins its own values | – |
| 2 | backend-python | A seam function returning vectors in request order, with tokens and USD cost | empty input rejected before any call; order restored from `index`; a width mismatch refuses rather than degrades; absent usage → zeros and `None`; no `dimensions` ever sent | I2 · WI1 |
| 3 | backend-python | `app llm embed` prints each vector's length, then the usage line | several texts in one invocation; `--model` override; failure prints the generic line and exits 1; `--details` as in sprint 02 | I3 · WI1 |
| qa | qa | Black-box acceptance tests for AC3–AC5 | all through the sprint-02 mock seam, no API key | I1–I3 |

## Interfaces
Verbatim from `research.md → Interfaces`; binding. Summarised — read that file for the full text.

- I1: `settings.py` after `llm_retry_backoff_seconds` — `embedding_model: str = "openai/text-embedding-3-small"` and `embedding_dimensions: int = Field(default=1536, ge=1)`, both matching `.env.dist` (**no `.env.dist` change needed — both already exist there**). `tests/conftest.py` pins `EMBEDDING_MODEL=test/embedding-model` and `EMBEDDING_DIMENSIONS=4`.
- I2: `service.py` — frozen `EmbeddingResult(vectors: list[list[float]], usage: Usage)` and `embed_texts(texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult`. Empty `texts` → `LlmBadRequestError` before any network call. One `_attempt()` closure through `call_with_retry(_attempt, label="embed")`, rebuilt per attempt exactly as `chat()` does. Calls `build_sdk_client(key).embeddings.generate(input=list(texts), model=…)` — **never `dimensions`, never `encoding_format`**. Malformed shapes → `LlmMalformedError`; width mismatch → `LlmConfigurationError` naming both env vars and the real width. `Usage(prompt_tokens, 0, total_tokens, cost)`; absent usage → `Usage(0, 0, 0, None)`.
- I3: `commands.py` — extract `_cost_text(usage)` and `_report_failure(exc, *, details) -> typer.Exit` from the existing `chat` body, leaving `_usage_line`'s output byte-identical and `chat`'s behaviour unchanged. New `embed` command: texts positional and space-separated, `--model`, `--details`. Output is one `vector N: length=…` line per vector in request order, then `tokens: prompt=… total=… · cost: …` — the chat line's shape minus `completion=`, which this endpoint does not return.

## Acceptance tests (qa)
- AC1/AC2 → hand-run by the human with a real key; no automated test.
- AC3 → several texts in one call return one vector each, in request order, including when the response's `index` values arrive shuffled.
- AC4 → the eight sprint-02 codes raised here too, asserted through the mock transport with no key.
- AC5 → the serialised request body contains **no** `dimensions` key, and a returned width differing from the setting refuses loudly.

## Order
Wave 1: WI1 alone. Wave 2, parallel: WI2, WI3, qa.

**What the research overturned, and the one judgement call:**
1. The intent research assumed LangChain drops `usage.cost` so embeddings needed raw `httpx`. **Wrong** — `openrouter` 0.10.8 exposes `client.embeddings.generate(...)` and its response carries `usage.cost` first-class. Same SDK, same exception types, so `classify()` and `call_with_retry` are reused unchanged and no new dependency is added.
2. A returned width differing from `EMBEDDING_DIMENSIONS` raises `LlmConfigurationError` — not one of the eight, not retryable. A silently wrong-width vector would corrupt phase 4/6's `vector(n)` column, and retrying a misconfiguration cannot help.
