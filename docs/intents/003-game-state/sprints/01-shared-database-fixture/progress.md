---
author: sprint
owner: agent
created: 2026-09-17
updated: 2026-09-17
stage: draft
---
# Progress: Sprint 01

| WI | Status | Note |
|---|---|---|
| 1 | done | `backend/tests/database.py`, `scratch_db(**env_pins)` per I1, commit 3a0d3e2 |
| 2 | done | `backend/tests/srd/conftest.py` down to 3 statements, commit 174c994; no SRD test module touched |
| 3 | done | `backend/tests/playthrough/{__init__,conftest}.py`, `playthrough_db` with no pins, commit 9053d07 |
| qa | done | 7 AC1 tests + 1 AC2 test, commits bddc28f and 86dd9f8 |

Status: `open | running | done | failed`

## Gates
`make lint` green · `make test` 550 backend + 53 frontend green · `make backend-test-db` 11 passed.
`git diff --stat main..HEAD` shows `tests/srd/conftest.py` as the only changed file under `tests/srd/` — AC1's "unchanged" holds.

## Issues
- WI2 returned without writing anything — it blocked waiting for WI1's file instead of coding against the fixed interface; one retry, then done.
- WI1 wrote its own behaviour tests at `backend/tests/test_database.py`; qa moved them to the plan's path and, in trimming, dropped AC1's "skips when no server answers" and the `test_<hex>` naming assertion. One retry restored both.
- Carried from research, unchanged by this sprint: the `database` tests skip under `make backend-test` because `--no-deps` leaves no server reachable, not because the marker deselects them. On a machine with the dev stack up they run for real and pass. AC3 forbids redefining the target, so the behaviour stands.

## Backlog proposals

## Verify
