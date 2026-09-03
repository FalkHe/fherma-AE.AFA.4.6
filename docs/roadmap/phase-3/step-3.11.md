---
phase: 3
step: "3.11"
title: "Domain tools I: convention, catalogue search & spec comparison"
summary: The tool convention (Pydantic args → service → serializable result, capture collector), shared name→bike resolution, the catalogue_search and spec_comparison tools, and the app tools run CLI harness.
effort: 4
dependencies: ["2.1", "3.8"]
---

# Step 3.11 — Domain tools I

**Effort: 4** — the convention module and resolver are built once here and
repeated by every later tool; the two tools themselves are thin.

Binding contract: `docs/roadmap/phase-3/shared-knowledge.md` (§Tool result
schemas, §Agent-loop decisions). Agent: **backend-dev**.

## Outline

- `backend/app/llm/agents/tools/__init__.py`: the convention —
  `ToolContext` (dataclass: `session`, `chat`, `collector`), every tool has
  a Pydantic args schema (camelCase aliases), returns a JSON-serializable
  Pydantic result (pinned shapes in shared-knowledge), calls a service —
  **no SQL in tools**; `build_advisor_tools(ctx)` assembles the LangChain
  tool list (grows in 3.12–3.14). Tool calls execute sequentially over the
  job's one session.
- Name→bike resolution in
  `catalogue_search_service.resolve_name(session, name)`: exact slug match,
  then ILIKE/trigram, **approved models only**; unresolved → the pinned
  structured `{"unknownBike": name}` result (3.14 turns repeated mentions
  into backlog flags) — never an exception.
- `tools/catalogue_search.py`: reuses the 3.8 `SpecFilters` +
  `find_motorbike_ids`, returns the pinned result shape (capped at 12
  results with `totalCount`).
- `tools/spec_comparison.py` + a `catalogue_search_service` method: 2–4
  bike ids/names → the pinned `{bikes, rows}` shape — rows keyed by frozen
  camelCase spec field names, every field present, values aligned to bike
  order, nulls explicit ("unknown", never guessed); **verified specs of
  approved models only**.
- `backend/app/cli/tools.py`: `app tools run <tool-name> --args '<json>'`
  invoking any registered tool directly; registered in `cli/main.py`.
- Tests: comparison with missing specs, resolver precedence (slug beats
  ILIKE), unknown-name result, args-schema validation errors.

## Verification

- `docker compose exec app-web app tools run spec_comparison --args
  '{"names":["Honda CB500F","Suzuki GSR600"]}'` prints an aligned
  verified-spec table with explicit nulls; `catalogue_search` with an A2
  filter returns only approved, eligible models.

## Risks / notes

- The result schemas are frozen (3.10's renderers are built against them in
  parallel) — a field rename here breaks the other track silently.
