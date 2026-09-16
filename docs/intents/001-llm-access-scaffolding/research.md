---
author: fhit:architect
owner: agent
created: 2026-09-15
---
# Research: intent 001 — LLM access and prompt scaffolding

## Facts

**Codebase.** No LangChain/LangGraph/Langfuse dependency exists (`backend/pyproject.toml:6`-`17`);
`docs/general/backend-stack.md:12` claims otherwise and is logged as wrong (`docs/roadmap/Stage-01/README.md:375`).
`Settings` declares five fields, none about models (`backend/app/core/settings.py:10`), and `extra="ignore"`
(`:8`) lets `.env.dist` document unread vars — it already pins `OPENROUTER_API_KEY`, `CHAT_MODEL`,
`EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` (`.env.dist:30`-`42`). **There is no image-model entry, and
`.env.dist` is owner-only** (`…/README.md:310`). Langfuse creds and a bundled stack exist
(`.env.dist:60`, `compose.langfuse.yaml`); wiring is phase 11.

Postgres runs `pgvector/pgvector:pg16` (`compose.yaml:76`) but no extension and no vector column exist —
`backend/alembic/versions/0001_baseline.py` creates only `users`/`sessions`. **pgvector is phase 4/6 work, out of
scope here.** Already ruled, not open: the checkpointer is LangGraph's `AsyncPostgresSaver` in its own `checkpoints`
schema, which Alembic must ignore (`docs/general/model.md:227`-`231`); prompts are git-versioned files under the
module that uses them (`:247`, `:271`), and the pinned root `modules/game/prompts/` is a logged error — an id
resolves against its **owning capability's** prompt dir (`…/README.md:374`). Precedent for resolve-by-id:
`backend/app/modules/content/service.py:16`,`:51`-`80` (root constant, `v<n>` dirs, id regex) with the
`NotFound`/`Invalid` split at `…/content/errors.py:5`,`:11`. Failures reach the wire via
`ErrorCode`/`_ERROR_INFO`/`ApiError` (`backend/app/core/errors.py:17`,`:30`,`:48`). Tests pin env before import,
stub the DB session, never build an engine (`backend/tests/conftest.py:16`-`31`,`:39`); `filterwarnings=["error"]`. Cost per turn and per playthrough is graded, summed from the event stream
(`docs/general/requirement-map.md:28`).

**External** (docs-lookup, 2026-09-15; nothing is pinned, so this intent sets the floors). `langchain-openrouter`
0.2.8 — PyPI — is first-party, needs `langchain-core>=1.5.5` + `openrouter>=0.9.2`, and exports **`ChatOpenRouter`
only**: no embeddings class, no image helper (reference.langchain.com). It supports streaming, tool calling and
`with_structured_output`, and takes `model`, `temperature`, `max_retries`, `openrouter_provider`, `session_id`,
`trace` (docs.langchain.com). Also current: `langchain-core` 1.6.3 · `langchain-openai` 1.6.2 · `langgraph` 1.2.11 ·
`langgraph-checkpoint-postgres` 3.1.2 · `langfuse` 4.15.2 (PyPI). `ChatOpenAI(base_url=…)` reaches any
OpenAI-compatible gateway, but LangChain states plainly that **non-standard response fields are not supported** —
`usage.cost` is exactly such a field. OpenRouter (openrouter.ai) serves `POST /api/v1/chat/completions`; `POST /api/v1/embeddings` in **OpenAI request/response format**, carrying `openai/text-embedding-3-small`; `POST /api/v1/images` under **its own schema** (`model`, `prompt`, `resolution`, `aspect_ratio`, `stream`,
`provider.options`) returning base64 plus USD `usage`; and `GET /api/v1/generation`. `usage.cost` comes back on
every response (last SSE chunk when streaming); `usage:{include:true}` is a deprecated no-op. Status codes: 400 bad
params · 401 bad key · 402 out of credit · 403 moderation/guardrail (`error.metadata.reasons`, `flagged_input`) ·
408 timeout · 429 rate limit · 502 model down · 503 no provider. A mid-stream failure arrives **after** HTTP 200 as
`finish_reason:"error"` + `error.metadata.error_type`; a model refusal is `finish_reason:"content_filter"`.
Interrupt/resume needs a checkpointer + `thread_id` + `Command(resume=…)`, via
`AsyncPostgresSaver.from_conn_string(...)` then `await checkpointer.setup()` (langchain docs).

## Options

**1 — Seam shape.** Recommendation **A**: `chat_model(*, model=None, temperature=None) -> BaseChatModel`,
`embed_texts(texts)`, `generate_image(*, prompt, model=None) -> bytes`; `None` falls back to settings,
so phase 10 passes the run's values and phase 8 calls `.astream()`.

| Option | Pro | Con |
|---|---|---|
| A `core/llm/` module of functions **returning LangChain objects** | matches "services are modules of functions"; streaming and per-run overrides are plain constructor args; monkeypatchable | a factory per call — cache the model by (model, temperature) |
| B wrapper hiding LangChain behind own types | provider-swappable | re-implements astream/tools/structured output, and breaks the LangGraph interop phases 7–8 need |
| C settings only; callers build their own client | least code | no single failure classification, no single tracing point — misses the intent's goal |

**2 — Image generation.** OpenRouter **does** serve it, at `/api/v1/images` — but under its own schema,
and **no LangChain binding exists**. Recommendation **A**, though the AGENTS.md conflict is the human's
to rule (question 4); phase 7's placeholder is needed either way.

| Option | Pro | Con |
|---|---|---|
| A `httpx` call to `/api/v1/images` inside the seam | same credential and failure classification, one seam | not via LangChain → **conflicts with AGENTS.md**; needs an owner-only `.env.dist` entry |
| B deterministic placeholder only | zero risk, zero conflict | drops a visible phase-7 feature |
| C chat-completions image models (legacy) | stays inside LangChain | OpenRouter advises against it; `ChatOpenAI` drops the non-standard fields it needs |

**3 — Failure classification.** Proposed, each distinguishable from the facts above: `LLM_AUTH` (401) · `LLM_BUDGET`
(402) · `LLM_RATE_LIMIT` (429) · `LLM_TIMEOUT` (408 + client) · `LLM_REFUSED` (403, or
`finish_reason:"content_filter"`) · `LLM_UNAVAILABLE` (502/503, or mid-stream `finish_reason:"error"`) ·
`LLM_MALFORMED` (structured-output parse failure) · `LLM_BAD_REQUEST` (400). Retryable: rate limit, timeout,
unavailable, malformed once. Not: auth, budget, refused, bad request. **Context overflow is not separable** —
OpenRouter returns a generic 400, so it folds into `LLM_BAD_REQUEST` (ASSUMPTION).

**4 — Prompt assets.** Files on disk: already ruled, human-edited, diffable, and `content/service.py` is a working
precedent. DB rows add a migration and an unused write path; Langfuse-managed prompts make an optional service
load-bearing. Resolve `<capability>/<kind>/<id>` against the owning module's own `prompts/` dir — phase 10's
"effective prompt" is then a compose step returning the text, free.

**5 — Agent state.** `AsyncPostgresSaver` on the existing postgres, own `checkpoints` schema, `setup()` from a
Typer command (no job runner exists), schema excluded from Alembic's `include_object`. Own tables would
re-implement `Command(resume=…)`.

**6 — Proving it.** Fakes for the classification (a stub raising each status suits the suite's monkeypatch style)
plus **one Typer command per call kind** as the live round-trip, run by hand. Cassettes pin a recorded provider
shape into a warning-clean suite; live CI calls need a key. The register's failure-injection seam
(`…/README.md:311`) falls out of settings: an override base URL and a bogus model id.

## Open questions

- *product-visible* — Cost in **USD** (`usage.cost`) or tokens only? Decides whether the seam returns cost from
  day one; USD also closes the register's cost-source decision and avoids its `.env.dist` trap.
- *product-visible* — One generic "the DM stumbled" plus retry, or a distinct message per failure class? Decides
  how many of the eight codes reach the wire.
- *product-visible* — Image generation: A, B or C. A needs the owner to add an image-model entry to `.env.dist`.
- *human ruling* — AGENTS.md requires LLM access **through LangChain**; the image endpoint has no binding. Amend
  the rule to "through OpenRouter", or drop image generation.
- *technical* — Does `ChatOpenRouter` surface `usage.cost` in `response_metadata`? Docs are silent; verify against
  a live key. Fallback: `GET /api/v1/generation`.
