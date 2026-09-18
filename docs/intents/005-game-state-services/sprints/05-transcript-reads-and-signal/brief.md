---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 05: the transcript records, filters and reports its cost

## Task
Implement the transcript: the single `append_event` writer with per-type payload validation, the player-visible events read with `after=` paging, the owner-only cost sum as a CLI one-off, and the SSE `updated` signal. Document the event-id ordering caveat.

## Outcome
Events appended through `append_event` read back in order from `GET …/events?after=<id>` at `player` visibility with a
`dm` event absent but present in the table, `app playthrough cost <run-id>` prints the exact `SUM(cost_usd)` for the
owner and refuses a foreign run, and `GET …/stream` emits `{"type":"updated","id":…}` within one interval of a new
event and stops when the client goes away.

## Acceptance criteria
- AC1: `append_event(db, *, run_id, type, visibility, payload, turn_id=None, actor_member_id=None, usage=None)` validates `payload` against the per-type model of `playthrough/schemas.py` (shapes from `decisions/mechanics.md`) and is the only writer of `events`.
- AC2: `GET /api/v1/playthrough/campaign/{id}/events?after=<id>&limit=` returns `player` events ordered by id alone, `after` exclusive; a `dm` event written between two `player` events is absent from the response and present in the table (`@pytest.mark.database`).
- AC3: `app playthrough cost <run-id> --user <id>` prints per-run and per-turn `SUM(cost_usd)` as exact decimals (`CliRunner`); a non-member answers `NOT_FOUND`; no HTTP route exposes cost.
- AC4: `GET …/stream` is `text/event-stream`; a test reading via `client.stream` sees `{"type":"updated","id":…}` after an insert and a keepalive comment otherwise, and the generator ends on disconnect or after its bounded lifetime; membership gate on both routes.

## Decisions
← D9, D10, D12, D14 · research §C1, §C2, §E

## Assumptions
- SSE is starlette `StreamingResponse` polling `max(id)` on a settings-driven interval (default 2 s), keepalive comment, bounded lifetime — no `sse-starlette`, no background runner.
- `events.id` is the chronological key; the one-process monotonicity caveat (← §C2) is written into `docs/modules/playthrough.md`, not fixed with a sequence.
- Cost stays CLI + service until the developer drawer exists (← D14).

## Out of scope
No `awaiting` derivation (07) · no `turn_id` allocation, no turn route (phase 8) · no narration written by an LLM here · no frontend.
