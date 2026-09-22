---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 07

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | `_parse_sections` pops the heading stack by level (`service.py:170`), regex stays `#{1,4}`; skip-level unit test; README chunking paragraph | AC1: `# A` → `## B` → `#### C` → `#### D` yields siblings `A › B › C` and `A › B › D`; deeper-then-shallower (`#### C` → `### E`) closes C; existing chunk tests still pass | – |
| 2 | sprint lead | re-ingest against the real DB, re-run the 11 README floor queries, update README floor table + rule count; re-pin `RELEVANCE_FLOOR` only if the gap no longer brackets 0.60 | AC2–AC5 by running `app srd search`; chunk count stays 1750 | WI1 |

## Interfaces
- I1: `service.chunk_source(path) -> list[RuleChunk]` signature and `RuleChunk` shape unchanged; only `heading_path` values differ. `_HEADING_RE` unchanged.
- I2: README ownership — WI1 edits the chunking description in "Owns"/"Surface"; WI2 edits "Relevance floor" (table, rule count, both formerly wrong citations).

## Acceptance tests (qa)
- AC1 → unit test in `backend/tests/srd/test_chunk_source.py` (WI1).
- AC2–AC5 → manual CLI runs recorded in `progress.md` and `review.md` (WI2); no qa agent, corpus-level checks need the real gateway.

## Order
WI1, then WI2.
