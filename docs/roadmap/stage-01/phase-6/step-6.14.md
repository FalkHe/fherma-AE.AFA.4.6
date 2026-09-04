---
phase: 6
step: "6.14"
title: Fencing the provenance metadata the model reads
summary: retrieve_bike_knowledge's _model_view fences source_title and heading_path alongside the snippet text and caps both payload-side; the persisted tool_calls[].result / sources[] JSONB stays byte-identical (5.8 pin). The catalogue_search/spec_comparison payloads and the web-sourced column caps are audited and the results recorded — no migration.
effort: 3
dependencies: []
---

# Step 6.14 — Fencing the provenance metadata the model reads

**Effort: 3** — a contained change to one `_model_view`, two payload caps with
justified constants, prompt-prose alignment, tests, and two recorded audits;
the fencing mechanism (5.7/5.8) already exists.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (**D7** — what is
fenced and what deliberately is not; the **Theme mapping** note re-scoping 6.8:
payload-side caps only, *no migration*, and the audit result is a deliverable
even when it is "nothing to change") and the Phase-5 5.8 pin: fencing wraps
what the **model** reads, never what is persisted or served — if that
separation isn't achievable, **stop and report**. Scheduled **after M1** (the
M2 milestone is this step alone). Agent: **backend-dev**. Zero deviations — a
deviation is a stop-and-report.

**Environment:** stack up; **`docker compose restart app-worker` after
landing** (job-executed code — the 2b.4 pin). No migration: a fifth schema
need is a stop-and-report. This step must not touch the rendered-name work
(6.19) — only provenance metadata.

## Outline

- `backend/app/llm/agents/tools/retrieve_bike_knowledge.py`:
  - two module constants with a justifying comment:
    `MODEL_VIEW_TITLE_CHARS = 160` and `MODEL_VIEW_HEADING_PATH_CHARS = 160`.
    Justification to write into the comment: both columns allow 512 chars, and
    the heading trail is repeated on **every** chunk — worst case
    `MAX_SNIPPETS = 6` snippets × (512 + 512) chars ≈ 6 KB ≈ 1.5k tokens of pure provenance;
    160 chars keeps the head of a title/trail (the informative part — page
    titles and ATX trails front-load their subject) and bounds the overhead to
    ≈ 2 KB before the sentinels;
  - `_model_view`: each snippet's `sourceTitle` becomes
    `_fenced_text(title[:MODEL_VIEW_TITLE_CHARS])` and `headingPath` becomes
    `_fenced_text(path[:MODEL_VIEW_HEADING_PATH_CHARS])` when not `None`
    (`None` stays `None` — never fence a null), alongside the already-fenced
    `text`. Truncate **before** fencing so a sentinel is never cut. Everything
    outside `_model_view` is untouched: `execute` keeps recording the plain
    `model_dump`, so `tool_calls[].result` and `sources[]` stay byte-identical;
  - `DESCRIPTION`: extend the sentinel sentence to say each passage's text,
    **source title and heading trail** sit between the markers; both are
    attacker-controlled (the page's own `<title>` via
    `ingestion/service.py::_store_document` and its ATX headings via
    `services/chunking.py::heading_path` — cite D7 in the module docstring).
- **Audit 1 (record the result in the report, even if "nothing to change"):**
  `backend/app/llm/agents/tools/catalogue_search.py` and `spec_comparison.py`
  payloads for unfenced web-derived free text. Expected finding per D7: their
  `name` values and spec numbers pass the admin review gate (tools serve
  approved rows only) and are deliberately **not** fenced; `spec_comparison`
  already excludes the free-form `extra`/`source_hints` via
  `UNCOMPARED_SPEC_FIELDS`. If the audit finds anything outside that
  reasoning, stop and report — do not fence admin-reviewed identity.
- **Audit 2 (record the result):** remaining web-sourced columns for missing
  caps — expected finding, confirming the Theme-6.8 re-scope:
  `source_documents.source_url` (2048) / `source_title` (512) / `raw_path`
  (512), `chunks.heading_path` (512, chunker-truncated at write),
  `motorbike_images.source_url` (2048) all carry DB bounds;
  `content_markdown` is unbounded `Text` but model exposure is capped by
  `extraction_max_input_chars` and the chunk sizes. Conclusion to record: no
  missing DB bound, therefore no migration.
- Tests, in `backend/tests/llm/agents/test_tools.py` (extend the existing 5.8
  model-view tests): sentinels present around title and heading path in
  `_model_view`'s output; caps applied (title/path longer than the constants
  are truncated before fencing); `headingPath=None` passes through as `None`;
  and the 5.8-pin proof at test level — `execute`'s recorded payload for this
  tool equals the plain `result.model_dump(by_alias=True)`, fences and caps
  appearing **only** in the model view.

## Verification

- `make backend-test` + `make lint` green; `docker compose restart app-worker`
  done (a live check behaving like the old code almost always forgot this).
- Both audit results written into the step report **and** the
  `shared-knowledge.md` appendix — "nothing to change, per D7 / per the
  Theme-6.8 re-scope" is a valid and expected outcome, with the reasoning.
- Live byte-identity + poisoned title/heading smoke is the **M2 demo**
  (milestone table), not re-proven here; note that `app tools run` prints the
  *recorded* payload, not the model view, so the unit tests are the
  model-view proof at dev level.

## Risks / notes

- Fencing stays a mitigation, not a proof — the README "Known limitations"
  entry stands; 6.29 keeps it (D7).
- Sentinel + truncation cost: ~10 tokens per fenced field × up to 12 extra
  fields per call — well inside budget at `MAX_SNIPPETS = 6`.
- 6.19 and 6.23 later edit tool payloads and **must not drop these fences**
  (merge-friction list) — which is why the constants and the fenced-field list
  must land in shared knowledge.
- Append (`### Step 6.14`) to `shared-knowledge.md`: the two constants with
  values, the fenced-field list (`text`, `sourceTitle`, `headingPath`), and
  both audit verdicts.
