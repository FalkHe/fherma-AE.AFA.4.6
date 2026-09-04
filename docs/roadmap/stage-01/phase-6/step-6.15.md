---
phase: 6
step: "6.15"
title: Extraction writes the identity and the trims
summary: ExtractedSpec grows the identity fields (buildingline, model_name, year_from/to, type_codes, variants) reusing 6.10's validators, spec_extraction_service._assign_manufacturer becomes _assign_identity through product_service.assign_identity, and spec_extraction.md gains the naming pitfalls and the trim delta rule.
effort: 4
dependencies: ["6.10", "6.12"]
---

# Step 6.15 — Extraction writes the identity and the trims

**Effort: 4** — a schema extension with validators, a prompt rewrite, a service
change with a policy to preserve, tests, and a live ingestion smoke; the
patterns (`NON_SPEC_FIELDS`, `_assign_manufacturer`, fenced prompt) all exist.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (D1, D2, D6 — the
claim is never copied into typed columns here; hard rules). Detail source:
`docs/roadmap/stage-01/phase-6/model-naming-data-model.md` §2.4, §2.5, §6 (extraction rows) and
`docs/modules/model-naming.md` (the pitfalls). The validators are 6.10's
`backend/app/services/identity_validation.py` (`normalize_type_codes`,
`normalize_variants`, each returning `(kept, warnings)`) and the writer is
6.12's `product_service.assign_identity(session, motorbike, *,
manufacturer_id, buildingline, model_name, year_from, year_to, type_codes,
variants)` — **reuse both, do not re-implement them**; confirm against their
`## Landed decisions` entries. Agent: **backend-dev**. Zero deviations — a deviation
is a stop-and-report.

**Environment:** stack up (`make up`); `OPENROUTER_API_KEY`/`TAVILY_API_KEY`
configured; the 200-row backlog imported. **Restart `app-worker` after
landing** (`docker compose restart app-worker`) — ingestion runs in the worker.

## Outline

- `backend/app/llm/extraction.py`:
  - `NON_SPEC_FIELDS = ("manufacturer", "buildingline", "model_name",
    "year_from", "year_to", "type_codes", "variants")`. `SPEC_FIELDS`,
    `to_spec_values` and the `with_structured_output(..., method="json_schema")`
    chain are **untouched** (the `model_json_schema` required-all override
    covers the new fields automatically).
  - New fields on `ExtractedSpec`, all optional/defaulted, junk clamped to
    `None`/dropped, never an error: `buildingline: str | None` (`_to_text`,
    truncated to 64), `model_name: str | None` (`_to_text`, truncated to 128),
    `year_from: int | None` and `year_to: int | None` (new module constants
    `YEAR_MIN = 1900`, `YEAR_MAX = 2100`; out of window → `None`; a model-level
    `@model_validator(mode="after")` sets `year_to = None` when both are set
    and `year_to < year_from`), `type_codes: list[str]` (default `[]`;
    schema-level coercion only: string entries, trimmed, defensively capped at
    16) and `variants: list[dict[str, Any]]` (default `[]`, capped at 30 raw
    entries). The *real* validation — trim/upper/dedupe, regex, ≤ 8 codes;
    ≤ 20 variants, delta-only `specs` whitelist, recomputed `slug` — happens
    in `_assign_identity` through `identity_validation.normalize_type_codes`
    / `normalize_variants`, so their `warnings` are not lost inside a Pydantic
    validator.
  - New `to_identity_values(self) -> dict[str, Any]` returning exactly the
    keys `buildingline, model_name, year_from, year_to, type_codes, variants`
    as plain Python (no Enums) — the kwargs of `assign_identity` minus the
    manufacturer.
- `backend/app/llm/prompts/spec_extraction.md`: extend the numbered rules
  (after rule 13; the fencing section and reminder stay verbatim) with:
  - identity fields: `model_name` is the marketing model without the brand
    ("R 1300 GS", "MT-07"); `buildingline` the model family if the documents
    name one (GS, MT, CBR), else `null`; `year_from`/`year_to` the production
    range of **this generation** (`year_to` `null` while still built).
  - the two pitfalls, verbatim in spirit from `docs/modules/model-naming.md`:
    "**Displacement in the name is not the actual displacement** (an MT-09 is
    890 cm³, a KTM 1290 is 1301 cm³) — never derive `engine_cc` from the
    name" and "**Never invent a type code.** List in `type_codes` every
    manufacturer code the documents print (K50, SC82, RM33) — codes you did
    not read do not exist."
  - the delta rule: "The base trim's specifications go in the top-level spec
    fields. `variants` holds the *other* trims only, each with the specs that
    **differ from or are added to** the base and a short `description` — never
    a full spec set, and never the base itself."
- `backend/app/services/spec_extraction_service.py`: rename
  `_assign_manufacturer` → `_assign_identity(session, motorbike, extracted)`,
  called at the same point (after `upsert_draft_spec`). It keeps the "never at
  the cost of the run" policy: resolve the manufacturer via
  `manufacturer_service.normalize_name` + `get_or_create` (fall back to the
  row's existing `manufacturer_id` when extraction returned none); when
  `extracted.model_name is None`, assign the manufacturer only (today's
  behaviour) and **do not** call `assign_identity` — a full-object replace
  with nulls must not wipe an existing identity; otherwise call
  `product_service.assign_identity(...)` with `**extracted.to_identity_values()`.
  Any exception (`DuplicateModelError` included) → one `logger.warning`, the
  draft spec stands, the run continues. The normalisers' dropped-entry
  `warnings` are logged here **and** carried on a new
  `ExtractionResult.identity_warnings: tuple[str, ...] = ()` field — 6.17,
  which owns the `_extraction_stage` edit, feeds them to `_Run._warn` (this
  step does not touch `ingestion/service.py`; the merge-friction list pins
  that file to 6.17/6.21). The suggestion claim is **never read here** (D6).
- Tests: extend `backend/tests/llm/test_extraction.py` (year clamps, the
  `year_to < year_from` drop, truncation, the defensive schema caps,
  `to_identity_values` shape, `to_spec_values` unchanged)
  and `backend/tests/services/test_spec_extraction_service.py` (identity
  assigned; `model_name=None` → manufacturer only, no `assign_identity` call;
  a raising `assign_identity` does not fail the extraction).

## Verification

- `make backend-test` and lint green; `docker compose restart app-worker`.
- Live smoke — real backlog row **Yamaha MT-07** (claim `[RM04/RM17/RM33]`,
  2014–present): `app ingest run "Yamaha MT-07"`, wait for the operation to
  succeed, then
  `docker compose exec postgres psql -U postgres -d app -c "select model_name, year_from, year_to, type_codes, buildingline from motorbikes where slug like '%mt-07%' or query_name = 'Yamaha MT-07';"`
  shows a filled `model_name` and at least one source-printed type code. Do
  **not** assert exact values — behavioural acceptance is QA 6.30's job; this
  proves the pipeline writes the columns at all.

## Risks / notes

- **Resolved (2026-08-31) — read `D2b` before writing this step, it changes
  the outline.** The flag was right: a weaker re-extraction would have
  overwritten an admin-corrected identity. The contract now pins the fix as
  **D2b**: `assign_identity` stays a full-object replace, but *this* caller
  merges first — it reads the row's current identity and applies "an existing
  non-NULL value wins" per field, **unions** `type_codes` (codes are additive
  metadata), and writes `variants` only into an empty list. So the first
  ingestion fills everything, a re-ingestion fills only what is still
  missing, and a human's correction is permanent. The `model_name is None`
  skip stays as the cheap short-circuit. No owner decision was needed.
- The prompt grows ~20 lines; keep the fence markers and the trust-order rule
  untouched — 6.14's fencing tests must stay green.
- 6.17 builds directly on this step (it compares the claim against what this
  step extracted); 6.19/6.20 render and serve what it writes.
- Append (`### Step 6.15`) to `shared-knowledge.md`: the final
  `NON_SPEC_FIELDS` tuple, the `to_identity_values` keys, the
  `ExtractionResult.identity_warnings` field 6.17 wires up, and the
  `model_name is None` skip rule 6.17/6.18 must know about, and the exact
  per-field merge semantics D2b pins (later steps reason about them).
