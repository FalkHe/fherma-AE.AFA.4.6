---
author: intake
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 01: a chat call round-trips and reports what it cost

## Outcome
`app llm chat "<prompt>"` answers from the configured OpenRouter chat model and
prints that call's prompt/completion tokens and its USD cost.

## Acceptance criteria
- AC1: with a real `OPENROUTER_API_KEY`, `docker compose run --rm --no-deps app-cli app llm chat "Name one D&D condition."` prints the model's answer.
- AC2: the same run prints prompt tokens, completion tokens and USD cost for that call.
- AC3: `--model` and `--temperature` override per call; omitted, they fall back to `CHAT_MODEL` and the seam's default.
- AC4: `--stream` prints the answer incrementally, proving the seam hands the caller a streamable LangChain chat model.
- AC5: an empty key exits non-zero with a message naming the missing key, not a traceback.
- AC6: `AGENTS.md`, `docs/architecture.md` and `docs/general/backend-stack.md` say LLM access goes through **OpenRouter**, and `backend-stack.md` no longer claims a LangChain dependency that is absent.

## Decisions
← D1, D3

## Assumptions
- The seam is `core/llm/`, a module of functions returning LangChain objects (`chat_model(...) -> BaseChatModel`), not own wrapper types.
- `usage.cost` is read from `response_metadata`; if `ChatOpenRouter` drops it, the fallback is `GET /api/v1/generation`.
- This sprint pins the `langchain-core` / `langchain-openrouter` floors.

## Out of scope
Failure classification (02) · retries (03) · embeddings (04) · images (05) · tracing (phase 11) · storing per-run overrides (phase 10).
