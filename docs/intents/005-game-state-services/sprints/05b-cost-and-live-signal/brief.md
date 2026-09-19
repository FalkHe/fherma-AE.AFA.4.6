---
author: sprint
owner: human
created: 2026-09-19
stage: approved
---
# Sprint 05b: the run reports its cost and says when something is new

Half of the approved sprint 05, split on the product owner's instruction because one sprint carried four
surfaces. The other half is 05a, which must land first. Task, outcome and criteria are that brief's,
partitioned — nothing is added.

## Task
Implement the owner-only cost sum as a CLI one-off and the SSE `updated` signal over the transcript 05a writes.

## Outcome
`app playthrough cost <run-id>` prints the exact `SUM(cost_usd)` for the owner and refuses a foreign run, and
`GET …/stream` emits `{"type":"updated","id":…}` within one interval of a new event and stops when the client
goes away.

## Acceptance criteria
- AC3: `app playthrough cost <run-id> --user <id>` prints per-run and per-turn `SUM(cost_usd)` as exact decimals (`CliRunner`); a non-member answers `NOT_FOUND`; no HTTP route exposes cost.
- AC4: `GET …/stream` is `text/event-stream`; a test sees `{"type":"updated","id":…}` after an insert and a keepalive comment otherwise, and the generator ends on disconnect or after its bounded lifetime; membership gate on the route.

## Decisions
← D10, D12, D14 · research §C2, §E

## Assumptions
- SSE is starlette `StreamingResponse` polling `max(id)` on a settings-driven interval (default 2 s), keepalive comment, bounded lifetime — no `sse-starlette`, no background runner.
- Cost stays CLI + service until the developer drawer exists (← D14).

## Out of scope
The writer and the events read — both 05a · no frontend · no cost route, ever.
