---
author: fhit:architect
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 03: the corpus is ingested, and says what it cost

## Outcome
`app srd ingest` embeds the stored source and the corpus goes from empty to populated: the run prints
chunk count, tokens and USD cost, and `app srd status` then reports rows, model and ingest time.

## Acceptance criteria
- AC1: with a real `OPENROUTER_API_KEY`, `docker compose run --rm app-cli app srd ingest` completes and prints the `IngestReport` — source version, bytes, chunk count, token count, USD cost.
- AC2: `app srd status` immediately afterwards reports a non-zero rule count, the `EMBEDDING_MODEL` used and the ingest time, and exits 0 (it exited 1 in sprint 01).
- AC3: every row carries `heading_path`, `ordinal`, `text`, `token_count` and `embedding_model`, and its vector width equals `EMBEDDING_DIMENSIONS` (← D4).
- AC4: a gateway failure mid-ingest surfaces as the matching `LlmError` of the seam's eight codes and leaves no rows behind — the corpus stays empty rather than half-filled.
- AC5: nothing outside `modules/srd` reads or writes `srd_rules`; the only entry point is the CLI (← D1, D2).

## Decisions
← D1, D2, D3

## Assumptions
- Calls `core/llm`'s `embed_texts` unchanged — **this sprint cannot start until intent 001 backlog 04 lands it**.
- Chunks are embedded in batches; the report's cost is the sum of the batch usages.
- Fetch → store → chunk → embed → insert runs in one transaction, which is also what makes AC4 hold.
- The live run is a human one with a real key; CI asserts the path with `embed_texts` monkeypatched, as the suite does elsewhere.

## Out of scope
Re-ingest semantics (04) · search and the relevance floor (05, 06) · any caller of `require_corpus` (phase 5).
