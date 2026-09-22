---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 04 — a second ingest replaces the corpus

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Proof that re-ingest replaces wholesale: no production code change (sprint 03's `ingest` already does it, see research); unit tests for the gaps, one `database`-marked test running ingest twice, one README sentence on re-ingest semantics, and a live second `app srd ingest` with before/after `app srd status` | an `LlmError` on a *later* batch adds and commits nothing; delete → add_all → commit happen in that order inside one transaction; a changed fixture file changes the chunk count with it; `srd_db`: two ingests with stubbed `embed_texts` keep the row count, advance the ingest time and never duplicate a citation, and a third run with a duplicated citation rolls back leaving the second corpus intact | – |

Single WI, no qa agent: the sprint is verification of existing behaviour, and the live re-run is the human-visible proof.

## Interfaces
None new. Tests use the existing `srd_db` fixture (`backend/tests/database.py`, `backend/tests/srd/conftest.py`) and the `embed_texts` monkeypatch pattern from `test_ingest_service.py`.

## Acceptance tests (qa)
- AC1 → live: status before and after the second ingest (same count, later time), recorded in `progress.md`.
- AC2 → `database` test distinct-citation check + unique constraint from migration 0009.
- AC3 → unit test: failure on the second batch writes nothing; `database` test: failed third run leaves the second corpus.
- AC4 → unit test: modified fixture → different chunk count.
- AC5 → unit test on call ordering + `database` test (rollback).

## Order
WI1 alone.
