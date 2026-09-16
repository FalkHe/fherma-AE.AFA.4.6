---
author: fhit:architect
owner: agent
created: 2026-09-16
updated: 2026-09-16
---
# Research: sprint 004/03 — the corpus is ingested

## Facts

**The seam.** `embed_texts(texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult`
(`backend/app/core/llm/service.py:295`) returns `EmbeddingResult(vectors: list[list[float]], usage: Usage)`
(`:77`), `Usage(prompt_tokens, completion_tokens, total_tokens, cost_usd: float | None)` (`:69`).
`completion_tokens` is always 0 for embeddings (`:231`); `cost_usd` is the provider's `usage.cost`, absent →
`None` (`:238`). It sends **every** text in one HTTP request (`:324`) — **no internal batching, the caller
batches**. Empty input raises `LlmBadRequestError` before any call (`:314`). It is **synchronous and
blocking**, retries internally (`call_with_retry`, `:338`; budget `LLM_RETRY_ATTEMPTS=3`, malformed capped at
2, each wait ≤30 s — `retry.py:35,55,74`), request timeout 60 s (`service.py:66`). Vector width is checked
inside the seam: a width ≠ `EMBEDDING_DIMENSIONS` raises `LlmConfigurationError`, never a degraded vector
(`:284`).

**Eight codes** (`core/llm/errors.py:93-130`): retryable — `LLM_RATE_LIMIT`, `LLM_TIMEOUT`,
`LLM_UNAVAILABLE`, `LLM_MALFORMED`; not retryable — `LLM_AUTH`, `LLM_BUDGET`, `LLM_REFUSED`,
`LLM_BAD_REQUEST`. `LlmConfigurationError` is separate and never retried (`:77`). `str(exc)` is always the
one generic line; detail lives in `.provider_message` (`:56`).

**Batch size.** Per input ≤8,192 tokens, **per request ≤300,000 tokens across all inputs** (OpenAI API
reference, `developers.openai.com/api/docs/api-reference/embeddings/create` — context7). OpenRouter documents no array-length cap (`openrouterteam/docs`, `api_reference/embeddings.mdx` —
context7; openrouter 0.10.8, `embeddings.generate(input=…, model=…)`). `MAX_CHUNK_TOKENS = 800`
(`modules/srd/service.py:138`), so 256 chunks/request is ≤204,800 tokens worst case (safe); 512 would be
409,600 (over the cap). **Measured corpus** (`chunk_source` over the shipped `content/srd/v1/SRD_CC_v5.1.md`,
run in `app-cli`): 1,878,072 bytes, **2,132 chunks, 502,818 tokens**, max chunk 800 → **9 requests at 256**.

**Live cost.** `openai/text-embedding-3-small` prompt price `0.00000002` USD/token (OpenRouter model listing —
context7) → 502,818 × 2e-8 = **≈ $0.010**, one cent. A single batch costs about a tenth of a cent;
`_cost_text` already renders sub-microdollar as `<$0.000001` (`core/llm/commands.py:11`).

**Transactions.** Services commit; nothing uses `begin()` — the whole codebase's pattern is `db.add(...)`
then `await db.commit()` (`modules/users/service.py:25`). Sessions are lazy: no socket opens until a
statement runs (`core/db.py:33`, confirmed by `tests/srd/test_commands.py:6`). **One transaction spanning the
nine HTTP calls is unnecessary**: embedding everything first, then opening the write for insert + commit
(seconds), gives AC4's promise identically — a gateway failure raises before any statement runs, so the
corpus keeps exactly the rows it had (zero). Memory for 2,132 × 1,536 floats is ~100 MB, one-shot CLI, and
inserting batch-by-batch without committing costs the same memory *plus* a connection pinned for the run.

**Sum rule.** `IngestReport.cost_usd: float | None` (`schemas.py:41`). Sum the batches whose `cost_usd` is not
`None`; `None` only when no batch reported one — a partial sum is more honest than hiding real spend.
`token_count` stays the tiktoken total, as `--dry-run` reports it (`commands.py:86`), so the two runs compare.

**Existing CLI** (`modules/srd/commands.py:69`): `--dry-run` = fetch → chunk → build `IngestReport` → print;
the bare command exits 1 with `EMBEDDING_NOT_LANDED_MESSAGE` (`:40,71`) — that branch is what this sprint
replaces, the dry-run branch is untouched. `status` already opens its own session via `get_sessionmaker`
(`:46`).

**Test seams.** `monkeypatch.setattr(llm_service, "embed_texts", _fake)` where `_fake(texts, *, model=None)`
returns an object with `.vectors` / `.usage` (`tests/core/llm/test_commands_embed.py:38`) — so `srd/service.py`
must do `from app.core.llm import service as llm_service` and call attribute-style. **Gotcha:** the suite pins
`EMBEDDING_DIMENSIONS=4` (`tests/conftest.py:25`) while `srd_db` pins 1536 (`tests/srd/conftest.py:101`), so
`check_vector_width()` only passes under `srd_db` / `-m database`; other tests must pin it themselves.

## Work items

- **WI1 service**: `ingest` embeds the stored source in batches and writes the corpus — vectors first, one
  short write transaction after. Behaviours: chunk order preserved into rows; every row carries
  `source_version`, `heading_path`, `ordinal`, `text`, `token_count`, `embedding_model`, a 1536-wide vector;
  batches never exceed the request cap; report sums tokens and known costs; a failing batch leaves zero rows
  and re-raises the `LlmError` untouched; a width mismatch raises before any call.
- **WI2 CLI**: the bare `app srd ingest` runs the real thing — opens a session, prints the report (version,
  bytes, chunks, tokens, cost) plus one progress line per batch; any `LlmError` is one stderr line, exit 1, no
  traceback; `--dry-run` unchanged.
- **WI3 docs**: module README `Surface`/`Notes` describe the landed ingest and its cost line; the one
  architecture line that says "once ingest lands" (`docs/architecture.md:14`) is brought current.

## Interfaces

```python
# app/modules/srd/service.py  (WI1 → WI2)
EMBED_BATCH_SIZE = 256

async def ingest(
    db: AsyncSession,
    *,
    version: str = SOURCE_VERSION,
    on_batch: Callable[[int, int], None] | None = None,
) -> IngestReport: ...
```

`on_batch(chunks_done, chunks_total)` fires after each batch; the service never prints. `ingest` calls
`llm_service.embed_texts(...)` attribute-style and lets `LlmError` travel out unwrapped (AC4). WI2 catches
`LlmError` and `SrdError` only.

## Open questions

**Product-visible**
- AC4 says "one transaction". Holding one across ~9 gateway calls buys nothing and pins a connection; the
  user-visible promise — a failed run leaves the corpus empty rather than half-filled — is kept exactly by
  embedding first and writing once. Confirm the promise, not the mechanism, is what AC4 means.
- The run is roughly a minute of silence at 9 requests. Proposed: one progress line per batch. Accept, or
  stay silent until the report?
- A partly-unpriced run reports the sum of the costs the gateway did report. Acceptable, or should it say
  "cost unavailable" whenever any batch is missing one?

**Internal**
- Whether `app srd ingest` gains the `--details` flag `app llm …` has for provider text on failure.
