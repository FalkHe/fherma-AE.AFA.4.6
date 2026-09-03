---
phase: 6
step: "6.9"
title: "Refactor: rename motorbikes.name to query_name"
summary: Pure mechanical rename of the ORM attribute and column — one alter_column migration off c3a91f28b4d7, every call site and test updated, both product endpoints keep emitting `name` by reading `query_name`. Zero behaviour change, proven by byte-identical curl captures.
effort: 2
dependencies: []
---

# Step 6.9 — Refactor: rename `motorbikes.name` to `query_name`

**Effort: 2** — one `alter_column`, a mechanical sweep over ~15 files; no logic
changes anywhere, which is exactly what makes it small.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (hard rules —
migration 1 of 4; pinned wire shapes stay additive) and
`docs/roadmap/model-naming-data-model.md` §2.2 (`name` → `query_name`,
`String(160) NOT NULL`) and §6 (blast-radius rows for ingestion, tools, tests).
This is a refactor and **ships alone** (house rule): no new columns, no new
behaviour, nothing from 6.10 sneaks in. Agent: **backend-dev**. Zero
deviations — a deviation is a stop-and-report.

**Environment:** stack up (`make up`) for the captures. Alembic head at step
start is `c3a91f28b4d7` — anything else is a stop-and-report. Take the two curl
captures **before** touching any code.

## Outline

- New migration (`docker compose run --rm app-cli alembic revision -m "rename motorbikes name to query_name"`),
  `down_revision = "c3a91f28b4d7"`:
  `op.alter_column("motorbikes", "name", new_column_name="query_name")`;
  downgrade reverses it. House style: `backend/alembic/versions/20260831_1200_c3a91f28b4d7_add_motorbike_suggestion.py`.
- `backend/app/db/models/motorbike.py`: attribute `name` → `query_name`
  (`NAME_LENGTH` constant keeps its name; width unchanged); update the class
  docstring ("`query_name` keeps the phrase an admin typed …").
- Call sites, all mechanical `Motorbike.name`/`.name` → `query_name`:
  - `backend/app/services/product_service.py` — `create_backlog`'s
    `Motorbike(name=…)` → `Motorbike(query_name=…)`; its `name` *parameter* and
    docstrings stay.
  - `backend/app/services/ingestion/service.py` — the two `self.motorbike.name`
    reads (Wikipedia lookup, web search; lines ~232/~252).
  - `backend/app/services/catalogue_search_service.py` — every `Motorbike.name`
    column reference (shortlist order, browse select/sorts, substring leg,
    verified-specs select; ~9 sites). The read-model dataclass fields
    (`VerifiedSpecs.name`, `BrowseRow.name`) **keep their names** — only the
    ORM attribute renames.
  - `backend/app/api/endpoints/products.py` — `_resource`'s
    `name=motorbike.name` → `name=motorbike.query_name`; the wire key `name`
    is untouched. `flag_unknown_bike` and `app/cli/seed.py`/`suggestions.py`
    only call `create_backlog(session, name)` — confirm no attribute access,
    change nothing there.
- Tests — mechanical `Motorbike(name=…)` → `Motorbike(query_name=…)` in the 10
  files that construct one: `tests/api/test_catalogue_models.py`,
  `tests/cli/test_suggestions.py`, `tests/llm/agents/test_advisor.py`,
  `test_advisor_qa.py`, `test_licence_cost_tools_qa.py`, `test_tools.py`,
  `test_tools_qa.py`, `tests/services/test_catalogue_search_service.py`,
  `test_rag_pipeline_service.py`, `test_rag_pipeline_service_qa.py` — plus any
  `motorbike.name` attribute reads the sweep finds.
- Final sweep must come back empty:
  `grep -rn "Motorbike(name=\|motorbike\.name\b\|Motorbike\.name\b" backend/app backend/tests`.

## Verification

- **Byte-identical captures** (the zero-behaviour-change proof): before any
  change, log in as the dev admin (`curl -s -c /tmp/jar -H 'Content-Type: application/json' -d '{"username":"<admin>","password":"<pw>"}' localhost:8000/api/auth/login`)
  and capture `curl -s -b /tmp/jar localhost:8000/api/products | jq -S . > before-products.json`
  plus `curl -s 'localhost:8000/api/catalogue-models?sort=name' | jq -S . > before-catalogue.json`.
  After landing (and `docker compose restart app-web`): re-capture and
  `diff` both — **empty diff required**.
- Migration round trip inside the container:
  `docker compose run --rm app-cli alembic upgrade head`, `downgrade -1`,
  `upgrade head`; paste output. `docker compose exec postgres psql -U app -d application -c '\d motorbikes'`
  shows `query_name`, no `name`.
- `make backend-test` and `make lint` green; the grep sweep output (empty)
  in the report.

## Risks / notes

- 6.10 edits the same model file and its migration chains onto this one —
  land and commit this step before 6.10 starts. 6.11's `NameParts.query_name`
  and D5's fallback read this attribute.
- The blast-radius table says "~9 test files"; the actual count is 10 (listed
  above). Not a contract conflict — the grep sweep is authoritative.
- Do not "improve" anything on the way (no sort changes, no rendered names —
  that is 6.11/6.19). Behavioural acceptance stays with QA 6.30.
- Append (`### Step 6.9`) to `shared-knowledge.md`: the migration's revision
  id (6.10 chains on it) and confirmation both captures diffed empty.
