# Phase 2b — Manufacturers table (interlude)

**Goal:** Turn the motorbike's manufacturer from a free-text column into a
first-class record that ingestion fills automatically.

**Why a "2b" existed:** an owner-requested refactor arrived after Phase 2 closed
but before the Phase 3 advisor work was dispatched. Building chat and retrieval
on a data model already known to be wrong was unacceptable; a full numbered
phase would have renumbered every later phase. Hence four backend-only steps.

## Delivered

- `manufacturers` table (name, unique slug, plus description and logo path
  reserved for later) and an FK on motorbikes; the free-text column was dropped
  in the same migration after its values were carried over.
- Zero-impact API change: products still return a `manufacturer` name, now
  derived. The generated frontend client came out byte-identical — no frontend
  work at all.
- Automatic brand capture on ingest: extraction also asks for the brand, then
  finds-or-creates the record. An unclear brand is logged and skipped — it never
  costs the run its extracted specs.
- `catalogue set-manufacturer` CLI, which backfilled the three existing approved
  bikes and remains the only manual correction path.
- Admin-only read-only `/api/manufacturers` list and detail. No create/edit/
  delete — records appear only via ingestion or the CLI.
- Independent QA acceptance: 7/7 criteria, tagged `phase-2b-done`.

## Non-obvious decisions

- Backfill by CLI, never by re-ingesting — re-ingestion deletes and rebuilds
  documents and embeddings, and Phase 3 depended on the three approved, embedded
  models surviving (embedding count verified unchanged).
- The legacy column was dropped rather than kept in sync: one source of truth,
  API shape preserved by derivation. Cost: migration and derived attribute had
  to land in one step, since either alone breaks the API.
- Dedupe keys on the slug, not the typed text, so "BMW ", "bmw" and "BMW"
  collapse. Accepted consequence: a migration round-trip regenerates record ids
  — assignments survive by name, ids are not stable.
- Brand is deliberately outside the frozen spec-column set; the LLM schema
  requires every property to be declared mandatory, so the field rides along in
  the extraction schema but routes to a different table.
- Admin-only even for reads, matching Phase 2; customer exposure left to Phase 4.

## Not delivered / deferred

- Admin UI for managing manufacturers — out of scope by owner decision.
- Description and logo content — columns exist, stay empty until an admin
  surface exists.
- Customer-facing manufacturer filter — deferred to Phase 4 (step 4.2).
- Operational finding: the worker does not hot-reload after data-model changes
  and must be restarted. Affects every later phase.
