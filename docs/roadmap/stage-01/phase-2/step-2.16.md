---
phase: 2
step: "2.16"
title: LLM foundation (OpenRouter via LangChain)
summary: The canonical model factory (get_chat_model via langchain-openrouter — never the OpenAI API), the Jinja prompt loader with StrictUndefined, a pluggable Langfuse callback slot, and an `app llm ping` smoke command — plus an early embeddings-route smoke check.
effort: 2
dependencies: ["0.1"]
agent: backend-dev
track: backend
---

# Step 2.16 — LLM foundation (OpenRouter via LangChain)

**Effort: 2** — small and foundational: everything LLM-shaped in Phases 2–5
goes through this module. Independent of the mainline — parallelizable.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *LLM decisions* (factory
shape, pinned default models, prompt loader rules, the
**OpenRouter-only rule**: if OpenRouter cannot serve a capability, stop and
report — never wire another provider). `docs/general/architecture.md` → *LLM / Agent
Architecture*, *Prompt Management*. Zero deviations.

## Files

- Create `backend/app/llm/__init__.py`, `models.py`, `prompts.py`
- Create `backend/app/llm/prompts/` (directory)
- Create `backend/app/cli/llm.py` (`ping` command)
- Create `backend/tests/llm/test_prompts.py`
- Modify `backend/app/core/config.py`, `.env.dist`
  (`OPENROUTER_API_KEY`, `CHAT_MODEL`), `backend/pyproject.toml` + `uv.lock`
  (`langchain`, `langchain-openrouter`, `jinja2`),
  `backend/app/cli/main.py`

## Implementation outline

- `models.py`: `get_chat_model(model: str | None = None)` —
  `ChatOpenRouter` per the pinned wiring (shared-knowledge → *LLM
  decisions*: version pin, `app_url`/`app_title`, `OPENROUTER_API_KEY`),
  `.env` default model, optional config-gated Langfuse callback slot (wired
  for real in Phase 5).
- `prompts.py`: load Markdown prompts from `app/llm/prompts/`, render with
  Jinja `StrictUndefined` — a missing variable raises, never renders silently.
- `app llm ping`: one trivial completion through OpenRouter, prints the
  model + reply.
- **Early risk retirement:** smoke-check OpenRouter's
  `POST /api/v1/embeddings` route once (temporary scratch call) with the
  pinned `EMBEDDING_MODEL` and **assert the vector length is 1536** —
  the route and model are documented as served (verified 2026-08-26), so
  this is a key/account sanity check; if it fails, stop and report.
- Run `make build` after the dependency change.

## Verification

- `make backend-test` green (prompt loader: renders with variables, raises
  on missing). Manual: `app llm ping` returns a completion; the embeddings
  smoke check result is stated in the step report.

**On finish:** append cross-step decisions (incl. the embeddings smoke
result) to `shared-knowledge.md` → *Landed decisions*.
