---
author: sprint
owner: agent
created: 2026-09-17
updated: 2026-09-17
stage: done
---
# Progress: Sprint 05

| WI | Status | Note |
|---|---|---|
| 1 | done | `Event` added to the module, README extended, engine-free model tests — 4b28a35 |
| 2 | done | revision `0006` after `0005` plus its engine-free test — 4c335b6 |
| 3 | done | 6 real-database acceptance tests — 77ebe11 |

Status: `open | running | done | failed`

## Issues
- The brief leaves this sprint's revision number open because it could have merged before 03 and 04. It did not, so it is settled: this is the sixth step, on top of the fifth.
- Ordering by id is provable rather than lucky: the id generator is monotonic within a millisecond, and the ids sort the same way in the database as in the application. Measured, not assumed.
- Three of the six commits carry their co-author line folded into the subject; two work-item agents also had to unpick each other's staged files, because all three ran in one working tree. Cosmetic here, but the shared tree is the cause and it will bite harder on a sprint where two agents touch one file.

## Gates
`make lint` green · `make test` 671 backend + 53 frontend · `make backend-test-db` 32 passed.

## Backlog proposals
- Write order by id is guaranteed within one process only. Two events written in the same millisecond by two workers could come back inverted. Nothing writes events yet and the append path is one transaction, but the phase that builds it should know.
- Sprint 02's `temperature` column is declared as a decimal in the database but annotated as a floating-point number in the model. Harmless while nothing writes it, wrong once something does. Not this sprint's business to correct.

## Verify
Round 1: approve — every criterion probed against a live database. Write order by id was shown to be provable rather than lucky: the generator is monotonic within a millisecond over twenty thousand ids, and the database sorts them exactly as the application does. The cost total comes back as an exact decimal, and no total is stored anywhere. No drift between the declared model and the migrated schema.

MR: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/21
