---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 02

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The caller's runs read as an enriched list: campaign title and summary, status, created date, adventures done of total, players at the table. A run whose pinned campaign content no longer loads is listed, flagged unavailable, with no campaign copy. | camelCase field set for a healthy run; newest first, archived included; completed count from the adventure rows; missing and broken content both yield the flag with null copy while a healthy sibling is unaffected and nothing raises; two runs of one campaign load content once; anonymous refused; the route holds no write | – |
| 2 | backend-python | One aggregate overview per run: the run, its members with username, role, a ready flag and the character's name when one exists, and the campaign's adventures in their own order with id, title, clipped intro excerpt and a done / active / unplayed status. An unavailable run answers with null copy and no adventures. | members carry username and role; ready false with null character name, true with the name once a character exists; a non-player creature must not make a member ready; adventures in campaign order with all three statuses; a long intro clipped at a word boundary, a short one verbatim; unavailable run answers null copy and an empty adventure list; non-member and unknown id refused alike; anonymous refused | WI1 |
| 3 | frontend | The typed API client is regenerated and committed so both reads are callable, the existing run shape untouched. | both new paths present; typecheck and lint pass | WI1, WI2 |
| qa | qa | Black-box acceptance tests, one per criterion. | AC1–AC5 | – |

## Interfaces
Verbatim from `research.md → Interfaces`: I1 routes, I2 service signatures, I3 schemas, I4 wire with content, I5 wire without content, I6 refusals. Each implementer receives the blocks it touches; none are renegotiable mid-sprint.

## Acceptance tests (qa)
- AC1 → read the list as a signed-in member; assert per run the campaign title, summary, status, created date and the two adventure counts; assert newest first and an archived run present.
- AC2 → a run pointing at content that no longer loads is still listed, flagged unavailable, campaign copy null, call succeeds.
- AC3 → read the overview; assert the run's facts, its members with username, role, ready flag and character name, and its adventures in campaign order with id, title, excerpt and status.
- AC4 → both reads leave run status and stored rows unchanged; a non-member is refused with the same code and envelope as the module's existing reads.
- AC5 → the committed generated client carries both new paths and the existing run shape unchanged.

## Order
Sequential: WI1, then WI2, then WI3. `qa` runs in parallel from the start.
