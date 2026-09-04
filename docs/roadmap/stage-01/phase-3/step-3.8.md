---
phase: 3
step: "3.8"
title: Query translation & spec-filter resolution
summary: An LLM structured-output pass rewriting conversational customer language into 1–3 retrieval queries plus typed spec filters, and the service resolving those filters to candidate bike IDs over verified specs of approved models.
effort: 3
dependencies: ["2.16", "2.17", "2.1"]
---

# Step 3.8 — Query translation & spec-filter resolution

**Effort: 3** — one prompt, one schema (built on the landed 2.17
structured-output pattern), one filter-to-SQL service; mostly
prompt/schema iteration.

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§Agent-loop
decisions — structured-output pattern). Agent: **backend-dev**.

## Outline

- `backend/app/llm/prompts/query_translation.md` (Jinja: customer utterance,
  recent-history summary block, active preferences; `StrictUndefined` —
  missing variables fail explicitly).
- `backend/app/llm/query_translation.py` (mirrors `extraction.py`):
  `TranslatedQuery` = `search_queries: list[str]` (1–3 rewrites),
  `spec_filters: SpecFilters`, `target_motorbike_names: list[str]`.
  `SpecFilters` mirrors the filterable frozen spec columns (category,
  seat-height max, power min/max kW, weight max kg, A2-eligible, price
  band, engine-cc range) using the pinned project units (mm, kg, kW, EUR).
  Reuse the 2.17 landed schema trick verbatim: `model_json_schema()`
  override listing **every** property in `required`, optionality as null
  unions, `with_structured_output(…, method="json_schema")`, no `strict`.
- `backend/app/services/catalogue_search_service.py` created **here** (3.11
  reuses it — no later refactor): `find_motorbike_ids(session, filters:
  SpecFilters) -> list[str]` over **verified** specs (`kind='verified'`) of
  **approved** models only.
- Translation runs on `get_chat_model()` (i.e. `CHAT_MODEL`) — it is a
  utility structured-output task like extraction, **not** the advisor's
  conversational model (`ADVISOR_MODEL` is 3.5/3.13's).
- Tests: a mapping-coverage test asserting `SpecFilters` covers every
  filterable frozen spec column (the drift guard — drift here silently
  empties retrieval), schema round-trip, filter-to-SQL clauses (mocked LLM
  throughout; no test reaches OpenRouter).

## Verification

- `uv run pytest` green including the mapping-coverage test; a
  smoke-render of the prompt with all variables succeeds.

## Risks / notes

- Unit conventions are frozen project-wide (Phase-2 spec table) — the
  schema validators normalize into them exactly as extraction's do.
- `SpecFilters` is reused by the 3.11 `catalogue_search` tool — keep it
  importable without the LLM machinery.
