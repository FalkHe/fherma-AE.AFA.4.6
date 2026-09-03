---
phase: 2
step: "2.17"
title: Spec extraction
summary: A Pydantic extraction schema mirroring the frozen spec column set (unit-normalizing validators, all-optional), a with_structured_output chain over Wikipedia-first truncated Markdown with untrusted-content prompt hygiene, an idempotent draft-spec upsert — hooked into the ingestion job + `app ingest extract-specs`. Merging this step is cross-track sync point S2.
effort: 4
dependencies: ["2.14", "2.16"]
agent: backend-dev
track: backend
---

# Step 2.17 — Spec extraction

**Effort: 4** — one prompt, one schema, one chain, but prompt iteration and
unit normalization take real time. The project's first production LLM call.
**Merging this step unblocks frontend step 2.20 (sync point S2).**

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *DB schema → core spec column
set* (the schema mirrors it 1:1 — frozen), *LLM decisions* (prompt rules,
token budget, untrusted-data hygiene), *Operation lifecycle* (extraction is
the 80 % milestone). Zero deviations; stop and report if one seems
necessary.

## Files

- Create `backend/app/llm/extraction.py` (Pydantic schema + chain)
- Create `backend/app/llm/prompts/spec_extraction.md`
- Create `backend/app/services/spec_extraction_service.py`
- Create mocked-LLM tests under `backend/tests/`
- Modify `backend/app/jobs/ingestion.py` (stage at 80 %,
  `Extracting specifications`), `backend/app/cli/ingest.py`
  (`extract-specs <slug>`), `backend/app/core/config.py`, `.env.dist`
  (`EXTRACTION_MAX_INPUT_CHARS`)

## Implementation outline

- Schema: all fields optional, mirrors the frozen columns exactly;
  validators normalize units (hp→kW, lbs→kg, etc.) and clamp junk to null;
  optional per-field `source_hints`. Category/price-band constrained to the
  pinned vocabularies (invalid value → null, not an error).
- Prompt: extraction only from the provided text; unknown = null; document
  content is **untrusted data** (fenced, instructions-resistant phrasing —
  baseline hygiene; full sweep is Phase 5.1).
- Input assembly: Wikipedia document first, each head-truncated to 12 000
  chars, total ≤ `EXTRACTION_MAX_INPUT_CHARS`.
- Service: run chain → validate → **upsert the `draft` row only** (re-run
  replaces the draft, never touches `verified`); `a2_eligible` derivation
  happens in the 2.1 spec-write path, not here.
- Ingestion stage failure handling: an extraction error is a warning (the
  admin can fill the form manually) — the job still reaches `in_review`.
- Timebox prompt tuning: "plausible cc/kW/seat height for the GSR 600" is
  the bar; the admin edit path is the correction mechanism by design.

## Verification

- `make backend-test` green (mocked LLM: unit normalization cases, junk →
  null, draft-only upsert idempotency).
- Manual: after `app ingest run "Suzuki GSR 600"`,
  `GET /api/products/<id>` shows `draftSpec` with plausible
  engineCc/powerKw/seatHeightMm; `app ingest extract-specs suzuki-gsr-600`
  twice → still exactly one draft row, `verified` untouched.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*, and **announce S2 is open** in the step report.
