---
author: fhit:architect
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 04: a second ingest replaces the corpus instead of growing it

## Outcome
Running `app srd ingest` a second time replaces the corpus wholesale — the row count is the same, nothing
is duplicated, and a run that fails part-way leaves the previous corpus intact.

## Acceptance criteria
- AC1: `app srd status` after a second `app srd ingest` reports the same rule count as after the first, with a later ingest time.
- AC2: no passage appears twice — a `heading_path` + `ordinal` pair is unique across the corpus after any number of runs.
- AC3: an ingest that fails after some chunks were embedded leaves the earlier corpus queryable and unchanged: `app srd status` reports the old count and old ingest time.
- AC4: a re-ingest of a *changed* stored source changes the row count and the file's diff together, so corpus and repository never disagree (← D3).
- AC5: the replacement is one transaction; no moment exists in which `app srd status` sees a partial corpus.

## Decisions
← D3

## Assumptions
- Replacement is delete-all + insert inside the ingest transaction, not a per-chunk upsert: no chunk id survives re-chunking, so hashing would be false economy.
- `source_version` stays `v1` unless the human bumps it; no second version directory here.
- AC3's failure is produced through the injection seam intent 001 sprint 02 established, never by editing the database.

## Out of scope
Search and the floor (05, 06) · corpus versioning beyond `v<n>` directories · any scheduled re-ingest (no job runner exists).
