---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 01 — empty corpus status

| WI | Status | Note |
|---|---|---|
| 1 | done | module shell, table, migration 0002, HNSW index; 16 engine-free tests; suite and lint green |
| 2 | done | corpus status, the empty-corpus guard and the width check; 7 unit tests |
| 3 | done | `srd status` wired into the CLI; empty exits 1 naming the ingest command; 4 unit tests |
| 4 | done | opt-in scratch-database fixture, `database` marker, `make backend-test-db`; live proofs of AC1/AC2/AC4 ride on it as qa's tests |
| qa | done | one acceptance test per criterion, AC1-AC5, black-box through the command and the live database |

Status: `open | running | done | failed`

## Issues
- The brief's third assumption is dead: intent 001 backlog 04 has landed, so `embed_texts`, `embedding_model` and `embedding_dimensions` already exist and this sprint declares none of them. The intent backlog's note calling 03–06 blocked on it is likewise stale.
- Two product-visible open questions decided by the sprint lead rather than escalated, both wording inside AC1's existing scope: the empty-corpus line names the ingest command as the next step; an un-migrated database keeps its raw database error, since teaching the command to say "not migrated" is outside every criterion here.
- `SrdVectorWidthError` is added to the module's error set although `decisions/module-structure.md` §3 does not list it — AC3 needs a distinguishable failure.
- The suite's global embedding width pin stays at 4; the real-database fixture overrides it per test, because the existing embedding tests build their vectors against the global value.

- `plan.md` is 537 words against a 500 cap; the overage is verbatim interface identifiers the parallel work items must share, not scope, so the sprint ran rather than being split.

- Two implementers staging commits at the same moment briefly swept one's files into the other's commit; the agent caught and reverted it, but parallel work items sharing one checkout make this a standing risk.

## Backlog proposals
- The empty-corpus message points the operator at the ingest command, which does not exist until sprint 03 — anyone following the hint before then gets an unknown-command error.
- `decisions/module-structure.md` §3 still lacks the vector-width error the code now raises; the attachment is the human's to amend.

## Gates
Lint, both test suites and the live-database run all pass (542 offline, 4 live, 53 frontend). One formatting-only fix applied to the acceptance test file at the gate; no assertion touched.

## Verify
Round 1: changes-requested. Every acceptance criterion and decision passed, and all three lead decisions were judged acceptable; the single failure was that the project's own test conventions and command list no longer described the new opt-in real-database path. Sent back to the work item that built it.
