---
phase: 2b
step: "2b.2"
title: Extraction fills the manufacturer + backfill CLI
summary: ExtractedSpec gains a manufacturer string (excluded from spec values); the extraction service get-or-creates and assigns the row after a successful spec upsert; a deterministic CLI backfills the three existing approved bikes without touching documents or embeddings.
effort: 3
dependencies: ["2b.1"]
agent: backend-dev
track: backend
---

# Step 2b.2 — Extraction fills the manufacturer + backfill CLI

**Effort: 3** — small additions to three known modules plus a 30-line Typer
command; the delicate parts are the frozen-spec-columns exclusion and the
never-fail-the-run policy.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *Extraction*, *CLI*,
*Services*, *Owner decisions* (backfill via CLI, never re-ingestion).
[`../phase-2/shared-knowledge.md`](../phase-2/shared-knowledge.md) — *LLM
decisions* and *Landed decisions* → Step 2.17 (the OpenRouter
`model_json_schema` / `required` constraint), Step 2.10/2.14 (ingestion run
semantics — understand why re-ingestion is forbidden here).
Zero deviations; stop and report if one seems necessary.

## Files

- Modify `backend/app/llm/extraction.py` (`manufacturer: str | None` on
  `ExtractedSpec`; **excluded from `to_spec_values()`**)
- Modify `backend/app/llm/prompts/spec_extraction.md` (brand only, no model
  suffix; untrusted-content hygiene unchanged)
- Modify `backend/app/services/spec_extraction_service.py` (after successful
  `upsert_draft_spec`: `normalize_name` → `get_or_create` →
  `assign_manufacturer`; null/empty → skip; failures logged, never fatal)
- Create `backend/app/cli/catalogue.py` (`app catalogue set-manufacturer
  <slug> "<name>"`); modify `backend/app/cli/main.py` (register — pinned
  merge-friction file)
- Tests under `backend/tests/` mirroring the touched modules (extraction
  schema, service behaviour, CLI via Typer `CliRunner`)

## Implementation outline

- Everything exactly as pinned in shared-knowledge *Extraction* and *CLI*.
- The manufacturer assignment happens only after the spec upsert succeeded;
  an exception in the manufacturer path must not fail the extraction run.
- CLI: unknown slug → stderr + exit 1 (the `fetch-image` precedent);
  success prints the manufacturer id/name.

## Out of scope

- `/api/manufacturers` endpoints (2b.3), admin UI, filling
  `description`/`logo_path`, re-ingesting any existing bike.

## Verification (dev — infrastructure)

- `make backend-test` and `make lint` green.
- Record chunk/embedding counts, then
  `docker compose run --rm app-cli app catalogue set-manufacturer
  <slug> "<Name>"` for each of the 3 approved bikes (Suzuki GSR600 →
  "Suzuki", Honda CB500F → "Honda", BMW S 1000 XR → "BMW"); psql: 3
  manufacturers rows, 3 FKs set, `documents`/`chunks`/embedding counts
  unchanged before vs after.
- `GET /api/products` now shows the three names in `manufacturer`.

**On finish:** append cross-step decisions (e.g. normalization edge cases)
to `shared-knowledge.md` → *Landed decisions*.
