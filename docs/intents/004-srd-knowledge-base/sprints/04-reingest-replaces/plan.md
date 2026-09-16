---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 04 — a second import replaces the corpus

## What is already true
Sprint 03 built replacement as "embed everything, then delete-all and insert in one transaction". That makes AC1, AC3 and AC5 already hold — but nothing proves them: every committed failure test starts from an empty corpus, and no test runs the import twice. Proving them is most of this sprint. Only AC2 and AC4 need code.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | No two stored passages can claim the same citation: the position a passage carries is unique within its heading trail, and the database refuses a duplicate rather than trusting the splitter. | two sections whose headings collapse to the same trail produce distinct positions; the database rejects a duplicate trail-and-position pair; a re-import of the real source still yields the same count | I1 |
| 2 | backend-python | A failed import leaves the stored rules file exactly as it was, so what the repository shows and what the corpus serves can never disagree. | an import that fetches a changed source and then fails while learning restores the previous file byte-for-byte; a successful import keeps the new file; the corpus is untouched in the failure case | I1, I2 |
| qa | qa | Black-box acceptance tests, one per criterion. | below | I1, I2 |

## Interfaces
- **I1** — `backend/app/modules/srd/service.py`: the position a chunk carries (`RuleChunk.ordinal`) is numbered per `heading_path` rather than per section, so collapsed heading trails cannot collide. New migration `backend/alembic/versions/0003_srd_rules_unique_citation.py`, `revision = "0003"`, `down_revision = "0002"`, adding a unique constraint over `(source_version, heading_path, ordinal)` on `srd_rules`, with `SrdRule` carrying the matching `__table_args__`.
- **I2** — `backend/app/modules/srd/service.py`: `ingest` restores the previously stored source file if it fails at any point after replacing it. No signature change.

## Decided here
- AC4's "corpus and repository never disagree" is read as binding: a failed import restores the previously stored file. Without that, a failure leaves the repository showing rules the corpus does not serve.
- The position a passage carries is now counted within its heading trail rather than within its markdown section. The approved module-structure attachment describes the old meaning; the trail is the citation, so uniqueness has to hold against the trail.

## Acceptance tests (qa)
- AC1 → asking for the corpus's state after a second import reports the same passage count as after the first, with a later import time.
- AC2 → no passage appears twice: a heading-trail-and-position pair is unique across the corpus after any number of runs.
- AC3 → an import that fails after some passages were learned leaves the earlier corpus queryable and unchanged — the old count and the old import time.
- AC4 → importing a changed source changes the passage count and the stored file together; a failure changes neither.
- AC5 → no moment exists in which the corpus is seen half-replaced.

## Order
WI1, then WI2 — both edit the same service. qa runs alongside from the start.
