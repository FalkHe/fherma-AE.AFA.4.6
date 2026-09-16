---
author: fhit:architect
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 01: the corpus reports that it is empty, and the vector width is checked

## Outcome
`app srd status` on a migrated, never-ingested database reports an empty corpus and exits non-zero, and a
vector width that disagrees with `EMBEDDING_DIMENSIONS` fails the same way instead of being accepted.

## Acceptance criteria
- AC1: after `alembic upgrade head`, `docker compose run --rm app-cli app srd status` prints an empty-corpus line (0 rules) and exits 1.
- AC2: the migration creates the `vector` extension, the `srd_rules` table of `decisions/module-structure.md` §2 and its HNSW `vector_cosine_ops` index — visible in `\d srd_rules`.
- AC3: with `EMBEDDING_DIMENSIONS` set to anything but the migration's width, `app srd status` exits non-zero naming the mismatch; it never truncates or pads.
- AC4: `srd_service.require_corpus()` raises `SrdCorpusEmptyError` on an empty corpus and returns nothing once rows exist.
- AC5: the suite gains a DB-backed test path proving AC1/AC4 against a real database, and the existing engine-free tests still pass with warnings as errors.

## Decisions
← D1, D2, D5 (the empty-corpus signal and the guard only — the playthrough-creation caller is phase 5)

## Assumptions
- Revision `0002_srd_rules`, rebased onto the current head; one `env.py` import line, as every module adds; `modules/srd/README.md` lands with it.
- The width is a literal `1536` in the migration, checked at runtime against `EMBEDDING_DIMENSIONS` in one place both `status` and `ingest` call.
- If intent 001 backlog 04 has not declared `embedding_model` / `embedding_dimensions` yet, this sprint declares them; `.env.dist` already carries both and is not touched.
- The real-engine fixture is opt-in and skips when no database is reachable, so the default suite stays green offline.

## Out of scope
Fetching, chunking, embedding, searching (02–06) · any caller of `require_corpus` (phase 5) · any HTTP surface (← D2).
