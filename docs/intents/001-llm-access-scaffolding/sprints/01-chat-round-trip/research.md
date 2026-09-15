---
author: fhit:architect
owner: agent
created: 2026-09-15
---
# Research: sprint 001/01 — a chat call round-trips and reports what it cost

## Facts

**Config.** `Settings` declares five fields, none about models (`backend/app/core/settings.py:10`-`14`);
`extra="ignore"` (`:8`) is why `.env.dist` already carries `OPENROUTER_API_KEY` (`.env.dist:30`) and
`CHAT_MODEL=openai/gpt-4.1-mini` (`:34`) unread — **no `.env.dist` change is needed** (owner-only file).
`get_settings()` is `@lru_cache`d (`:17`); `os.environ` is read nowhere but `settings.py`
(`docs/general/backend-stack.md:95`), so the seam passes `api_key=` explicitly.

**CLI precedent.** Sub-app in the owning package, registered in `app/cli.py:26`; root callback configures
logging (`:12`-`14`); failures are `typer.echo(..., err=True)` + `raise typer.Exit(code=1)`
(`app/modules/content/commands.py:16`-`17`,`:49`), stdout carries data only. Domain exceptions are a base plus
subclasses in the package's own `errors.py` (`app/modules/content/errors.py:1`,`:5`,`:11`); `core/errors.py`'s
`ErrorCode` (`:17`) is HTTP-wire only and gains nothing here — no route exists yet.

**Tests.** `backend/tests/conftest.py:16`-`21` pins env vars **before** `app` is imported, then clears the
settings cache (`:28`). `app-cli` loads the host `.env` (`compose.yaml:50`-`51`), so a real key sits in
`os.environ` during `make backend-test` — conftest must pin `OPENROUTER_API_KEY` to a dummy, or the suite
behaves differently per machine. `filterwarnings = ["error"]` (`backend/pyproject.toml:57`). CLI tests
use `CliRunner` with a separate `result.stderr` (`backend/tests/content/test_cli.py:22`,`:35`-`37`).
For AC6: `AGENTS.md:50` still says "through OpenRouter **via LangChain**" (← D1), and
`docs/general/backend-stack.md:12` calls LangChain "declared but not wired yet" — it is not declared at all.

**External — docs-lookup 2026-09-15, PyPI metadata + wheel source; nothing installed yet.**
`langchain-openrouter` 0.2.8 needs `langchain-core>=1.5.5,<2` (current 1.6.3) and `openrouter>=0.9.2,<1`, and
exports `ChatOpenRouter` only. Line refs below = wheel `langchain_openrouter/chat_models.py`.

- Constructor aliases (`:167`,`:172`,`:239`,`:243`): `api_key=`→`openrouter_api_key`,
  `base_url=`→`openrouter_api_base`, `model=`→`model_name` (**required**), `temperature: float | None = None`;
  `max_retries=2` means SDK backoff is already on — sprint 03's business. Streaming: `.stream()`/`.astream()`.
- **`usage.cost` survives — build no fallback.** `_create_chat_result` copies `usage.cost` and `cost_details`
  into `message.response_metadata` (`:862`-`866`); `stream_usage=True` (`:273`) sends
  `stream_options={"include_usage": True}`, so the final usage-only chunk carries the same (`:619`-`630`).
  Counts reach `message.usage_metadata` as `input_tokens`/`output_tokens`/`total_tokens` (`:860`).
  `GET /api/v1/generation` is **not** needed — this closes the intent's open technical question.
- Chunks add up (`merge_dicts` skips the repeated equal `model_provider`; `cost` appears once), so
  `total = chunk if total is None else total + chunk` yields one message: answer + usage + cost.
- Empty key: `validate_environment` raises `ValueError("OPENROUTER_API_KEY must be set.")` **at construction**
  (`:477`-`480`) — a traceback; the seam must check settings first (AC5).
- `message.text` is a property returning a `str` subclass; `message.text()` warns
  (`langchain_core/messages/base.py`, `TextAccessor`) — **fatal** under `filterwarnings=["error"]`.
- **Resolution trap.** `openrouter` 0.11.x caps `pydantic<2.13`, excluded by this project's `pydantic>=2.13.5`
  (`backend/pyproject.toml:11`); the highest uncapped release is **`openrouter==0.10.8`**, so that is what uv
  picks, and it has all `_build_client` touches (`chat.send`, `send_async`, `server_url`, `timeout_ms`,
  `utils.BackoffStrategy`/`RetryConfig`). Verify with `grep -A1 'name = "openrouter"' backend/uv.lock`. Each
  construction opens an `httpx.Client` + `AsyncClient` (`:446`-`452`) — no model caching this sprint.

## Work items

Python throughout → `backend-python`. WI2–WI5 run in parallel; only WI1 must land before anything *runs*.

- WI1 deps + config: `langchain-openrouter>=0.2.8` / `langchain-core>=1.6.3` in `backend/pyproject.toml`,
  `uv.lock` refreshed via `make build`; the two `Settings` fields; the two `tests/conftest.py` env pins.
  Proves the import is warning-clean and reports the resolved `openrouter` version.
- WI2 seam: `backend/app/core/llm/{__init__,service,errors}.py` — `chat_model()`, `usage_of()`, two exception
  classes. No CLI, no docs.
- WI3 CLI: `backend/app/core/llm/commands.py` plus one registration line in `app/cli.py` — plain and streaming
  paths, usage line, `LlmError` → stderr + exit 1.
- WI4 tests: `backend/tests/core/test_llm_service.py` + `test_llm_commands.py` — AC3/AC4/AC5 and AC2's
  formatting, offline against fakes. Repo convention gives test authorship to `qa-backend`.
- WI5 docs (AC6): `AGENTS.md:50`, `docs/architecture.md:15`, `docs/general/backend-stack.md:12`. Markdown only.

## Interfaces

- `backend/app/core/llm/service.py` (WI2), called as `from app.core.llm import service as llm_service`:
  - `chat_model(*, model: str | None = None, temperature: float | None = None) -> BaseChatModel` — `None`
    falls back to `get_settings().chat_model` and to module constant `DEFAULT_TEMPERATURE = 0.7`; raises
    `LlmConfigurationError` when `get_settings().openrouter_api_key` is blank, **before** constructing
    anything. `ChatOpenRouter` is a module-level name: WI4 monkeypatches `service.ChatOpenRouter` and asserts
    the `model=`/`temperature=` kwargs without a key (AC3).
  - `usage_of(message: BaseMessage) -> Usage`; `Usage` is a frozen dataclass `(prompt_tokens: int,
    completion_tokens: int, total_tokens: int, cost_usd: float | None)` from `message.usage_metadata` and
    `message.response_metadata.get("cost")`; absent → zeros and `None` (← D3).
- `backend/app/core/llm/errors.py` (WI2): `LlmError(Exception)` and `LlmConfigurationError(LlmError)`, message
  naming `OPENROUTER_API_KEY`. **Sprint 02 plugs in here**: its eight classes become further `LlmError`
  subclasses plus a `classify()` in this module, and WI3 already catches `LlmError` — no caller changes.
- `backend/app/core/llm/commands.py` (WI3): `llm_app = typer.Typer()`; command `chat`; argument `prompt: str`;
  options `--model` (`str | None`), `--temperature` (`float | None`), `--stream` (flag, off by default);
  registered as `cli.add_typer(llm_app, name="llm")` → `app llm chat "<prompt>"`. Stdout: the answer, then
  `tokens: prompt=<n> completion=<n> total=<n> · cost: $<cost_usd:.6f>` (`cost: unavailable` when `None`).
  `--stream`: iterate `model.stream(prompt)`, print `chunk.text` unbuffered, accumulate as above, then that
  line from `usage_of(total)`. `LlmError` → `typer.echo(str(exc), err=True)` + `Exit(code=1)`, no traceback.
- `settings.py` (WI1): `openrouter_api_key: str = ""`, `chat_model: str = "openai/gpt-4.1-mini"`;
  `tests/conftest.py` pins `OPENROUTER_API_KEY="test-key"` / `CHAT_MODEL="test/model"` alongside `:18`-`21`.
- AC1/AC2 are hand-run by a human with a real key in `.env`:
  `docker compose run --rm --no-deps app-cli app llm chat "Name one D&D condition."` (once more with
  `--stream` for AC4). Everything else is assertable offline against fakes.

## Open questions

- **No product-visible question is open — the sprint may start**: D1 and D3 settle both (rule wording;
  tokens *and* USD).
- *technical* — the `openrouter` version uv resolves under `pydantic>=2.13.5` is predicted, not observed; WI1
  confirms it from `backend/uv.lock` and returns `blocked` if resolution fails, never relaxing that floor.
