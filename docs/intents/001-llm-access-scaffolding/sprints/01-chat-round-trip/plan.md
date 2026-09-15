---
author: sprint
owner: agent
created: 2026-09-15
---
# Plan: Sprint 01 — a chat call round-trips and reports what it cost

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The project declares and resolves the LangChain floors, and config carries the key and chat model | import of `langchain_openrouter` is warning-clean; `Settings` exposes both fields; the suite runs with pinned dummy env whatever the host `.env` holds | – |
| 2 | backend-python | A seam that hands back a configured chat model and reads usage off a reply | model/temperature fall back to settings when omitted and are passed through when given; blank key raises before construction; usage reads tokens and cost, and degrades to zeros/`None` when absent | I1, I2, I4 · WI1 |
| 3 | backend-python | `app llm chat` answers, streams on request, and prints the usage line | plain and `--stream` paths both print answer then usage line; `--model`/`--temperature` reach the seam; `LlmError` exits 1 on stderr with no traceback | I3 · WI1, WI2 |
| 4 | backend-python | The three docs say LLM access goes through OpenRouter, and backend-stack stops claiming a dependency that is absent | – (markdown only) | – |
| qa | qa | Black-box acceptance tests for AC2–AC6 | one per criterion, offline against fakes | I1–I4 |

## Interfaces
Verbatim from `research.md → Interfaces`; the five below are binding.

- I1: `app/core/llm/service.py`, imported as `from app.core.llm import service as llm_service` —
  `chat_model(*, model: str | None = None, temperature: float | None = None) -> BaseChatModel`. `None` falls back to `get_settings().chat_model` and module constant `DEFAULT_TEMPERATURE = 0.7`. Raises `LlmConfigurationError` when `get_settings().openrouter_api_key` is blank, **before** constructing anything. `ChatOpenRouter` is a module-level name so tests can monkeypatch `service.ChatOpenRouter`.
- I2: same module — `usage_of(message: BaseMessage) -> Usage`; `Usage` is a frozen dataclass `(prompt_tokens: int, completion_tokens: int, total_tokens: int, cost_usd: float | None)`, read from `message.usage_metadata` and `message.response_metadata.get("cost")`; absent → zeros and `None`.
- I3: `app/core/llm/commands.py` — `llm_app = typer.Typer()`, command `chat`, argument `prompt: str`, options `--model` (`str | None`), `--temperature` (`float | None`), `--stream` (flag, default off). Registered `cli.add_typer(llm_app, name="llm")` → `app llm chat "<prompt>"`. Stdout: the answer, then `tokens: prompt=<n> completion=<n> total=<n> · cost: $<cost_usd:.6f>`, or `cost: unavailable` when `None`. `--stream` iterates `model.stream(prompt)`, prints `chunk.text` unbuffered, accumulates `total = chunk if total is None else total + chunk`. `LlmError` → `typer.echo(str(exc), err=True)` + `Exit(code=1)`.
- I4: `app/core/llm/errors.py` — `LlmError(Exception)`, `LlmConfigurationError(LlmError)` whose message names `OPENROUTER_API_KEY`. Sprint 02 extends here; WI3 catches `LlmError` so 02 needs no caller change.
- I5: `settings.py` — `openrouter_api_key: str = ""`, `chat_model: str = "openai/gpt-4.1-mini"`. `tests/conftest.py` pins `OPENROUTER_API_KEY="test-key"` and `CHAT_MODEL="test/model"`.

## Acceptance tests (qa)
- AC1 → hand-run by the human with a real key; no automated test.
- AC2 → usage line format asserted off a faked reply carrying `usage_metadata` + `response_metadata["cost"]`.
- AC3 → `--model` / `--temperature` reach `ChatOpenRouter`; omitted, the settings values do.
- AC4 → `--stream` prints incrementally and still emits one usage line from the accumulated message.
- AC5 → blank `OPENROUTER_API_KEY` exits 1, message names the variable, stderr carries no traceback.
- AC6 → the three files assert as fixtures: text present, and no "via LangChain" left in `AGENTS.md`.

## Order
Wave 1, parallel: WI1, WI4, qa. Then wave 2, parallel: WI2, WI3.
`chunk.text` is a property — `chunk.text()` warns and `filterwarnings = ["error"]` makes that fatal.
