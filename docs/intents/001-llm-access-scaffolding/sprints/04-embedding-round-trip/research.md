---
author: fhit:architect
owner: agent
created: 2026-09-15
---
# Research: sprint 001/04 — an embedding call round-trips and reports what it cost

## Facts

Read and **executed** in `app-cli` vs. `httpx.MockTransport`, 2026-09-15, local site-packages:
`openrouter` 0.10.8 · `langchain-openrouter` 0.2.8 · `langchain-core` 1.6.3.

**The intent research's premise is obsolete; neither LangChain nor raw `httpx` is needed.** The SDK
carries this call: `client.embeddings.generate(input=…, model=…)` (`openrouter/embeddings.py:21`) → `POST
https://openrouter.ai/api/v1/embeddings` (verified URL). `langchain_openrouter` still exports
`ChatOpenRouter` only (verified `dir()`), so `OpenAIEmbeddings` meant `langchain-openai` as a **new
dependency** plus its dropped-field problem, and raw `httpx` meant losing the `OpenRouterError` types
`classify()` matches on. The SDK costs neither.

**D3 is satisfied — `usage.cost` is a modelled field here, not an extra to scrape.**
`CreateEmbeddingsUsage`: `prompt_tokens: int`, `total_tokens: int`, `cost: Optional[float]`
(`openrouter/operations/createembeddings.py:449`,`:452`,`:455`), `usage` itself `Optional` (`:526`);
executed, `cost=1.4e-06` arrived intact. **The endpoint has no completion-token count.**

**`classify()` needs no extension; all eight codes stay reachable.** `generate()` declares the same
`error_status_codes` as chat (400/401/402/404/429/4XX/500/502/503/524/529/5XX, `embeddings.py:80`-`93`)
and raises the same `openrouter.errors.*` classes. Executed: 502 → `BadGatewayResponseError(status_code=
502)` · 403 → `OpenRouterDefaultError(status_code=403)` (no 403 branch; `4XX` catches it, `.status_code`
intact) · a 200 with a junk body → `ResponseValidationError(status_code=200)` → `LLM_MALFORMED`.
`retry_config=None` (`app/core/llm/service.py:56`) kills the SDK's own 5XX backoff here too — 0.01 s.
**AC5 is free**: `dimensions` is in the request serializer's `optional_fields` (`createembeddings.py:225`)
and dropped when unset — the body sent was exactly `{"input": [...], "model": "..."}`.

**Order is not guaranteed by the type.** `CreateEmbeddingsData.index` is `Optional[int]`
(`createembeddings.py:340`) and the SDK preserves the provider's order (a mock returning index 1 then 0
came back that way). `embedding` is `Union[List[float], str]` (`:335`), the `str` being base64. A 200 with
`content-type: text/event-stream` returns a **bare `str`, not a model** (`embeddings.py:85`, verified): no
exception raised, so only the seam can see either.

**Codebase.** `Settings` has neither embedding field (`app/core/settings.py:16`-`19`), but `.env.dist:43`
-`51` documents `EMBEDDING_MODEL` and `EMBEDDING_DIMENSIONS=1536` — **the owner-only file needs no edit.**
`tests/conftest.py:22`-`23` pins env before importing `app`, and must pin these two. Reused as is:
`build_sdk_client()` (`service.py:45`), `Usage` (`:37`), `call_with_retry` (`retry.py:113`), `classify()`
(`errors.py:200`), the CLI failure block (`commands.py:38`-`54`).

## Work items

WI1 first, then WI2 ∥ WI3, then WI4. All `backend-python`; WI4 `qa-backend`.

- WI1 (AC1, AC5) `app/core/settings.py` + `tests/conftest.py` pins + `tests/core/test_settings.py`.
- WI2 (AC1–AC3, AC5) `app/core/llm/service.py`: `EmbeddingResult`, `embed_texts()`.
- WI3 (AC1–AC3) `app/core/llm/commands.py`: the `embed` command + a shared failure helper.
- WI4 (AC3, AC4) `tests/core/llm/test_embeddings.py` + a CLI case in `test_commands.py`.

## Interfaces

- **WI1** `app/core/settings.py`, after `llm_retry_backoff_seconds`: `embedding_model: str =
  "openai/text-embedding-3-small"` · `embedding_dimensions: int = Field(default=1536, ge=1)` — both match
  `.env.dist`. `tests/conftest.py` beside `:23`: `EMBEDDING_MODEL=test/embedding-model`,
  `EMBEDDING_DIMENSIONS=4` (a small width keeps WI4's fakes readable). `test_settings.py` asserts both
  defaults via its `Settings(_env_file=None, …)`/`monkeypatch.delenv` pattern (`:36`-`47`), and
  `embedding_dimensions=0` raising `ValidationError`.
- **WI2** `app/core/llm/service.py`: frozen dataclass `EmbeddingResult(vectors: list[list[float]], usage:
  Usage)` and `embed_texts(texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult`.
  - Empty `texts` → `LlmBadRequestError()` before any network call. Otherwise one `_attempt()` closure run
    through `call_with_retry(_attempt, label="embed")`, rebuilt per attempt like `chat()` (`:116`-`127`):
    blank `openrouter_api_key` → `LlmConfigurationError()`; then `build_sdk_client(key).embeddings
    .generate(input=list(texts), model=model or settings.embedding_model)` — **no `dimensions`, no
    `encoding_format`, ever (← AC5)**; then `chat()`'s own `except Exception` / `classify()` / re-raise.
  - Response, in order. A non-`CreateEmbeddingsResponseBody` return (the SSE `str`), a `str` `embedding`
    or `len(data) != len(texts)` → `LlmMalformedError()`; then sort `data` by `.index` when **every** item
    has one, else keep response order; then any vector whose length differs from
    `settings.embedding_dimensions` → `LlmConfigurationError` naming both env vars and the real width.
  - `Usage(prompt_tokens=u.prompt_tokens, completion_tokens=0, total_tokens=u.total_tokens,
    cost_usd=u.cost)`; `usage is None` → `Usage(0, 0, 0, None)`. `usage_of()` is chat-only, untouched.
- **WI3** `app/core/llm/commands.py`:
  - `_cost_text(usage) -> str` extracted from `_usage_line` (`:11`) — `"unavailable"` / `f"${…:.6f}"`,
    with `_usage_line`'s own output byte-identical.
  - `_report_failure(exc: LlmError, *, details: bool) -> typer.Exit` — the body of `:43`-`54` verbatim
    (generic line, `details: …` only when asked, **never `.body`/`.headers`/`.raw_response`); it *returns*
    the `Exit`, so both call sites keep `raise … from exc`. `chat` switches to it unchanged.
  - `@llm_app.command("embed")` `def embed(texts: list[str] = typer.Argument(...), model: str | None =
    typer.Option(None, "--model"), details: bool = typer.Option(False, "--details"))` — texts are
    **positional, space-separated** (`app llm embed "a" "b"`), Typer requires at least one. One line per
    vector in request order, then usage: `vector 1: length=1536` … `tokens: prompt=7 total=7 · cost:
    $0.000001` — `chat`'s `tokens: … · cost: …` shape minus `completion=`, which this endpoint lacks.
- **WI4** monkeypatches `service.build_sdk_client` onto `httpx.MockTransport` (sprint 02's seam,
  `service.py:45`), never `service.ChatOpenRouter`. Cases: shuffled `index` restored (AC3) · absent `usage`
  → zeros / `unavailable` · the eight statuses asserting `exc.code` (AC4) · SSE-`str` and wrong-count
  bodies · width mismatch · **no `dimensions` key** in the request body (AC5). AC1/AC2: a human, real key.

## Open questions

- **None product-visible — the sprint may start.** D3's USD requirement is met by the endpoint itself
  (`usage.cost`); there is nothing for the human to rule on. Below are my calls, for veto.
- *technical* — a width mismatch raises `LlmConfigurationError` (own message, not one of the eight, not
  retryable) rather than degrading: a silent 3072-wide vector would corrupt phase 4/6's `vector(n)` column,
  and retrying a misconfiguration cannot help.
- *technical* — counts are `prompt` and `total` only, so no `completion=` on the embed line; and order is
  restored from `index` only when every item carries one, a partial set giving nothing to sort on.
