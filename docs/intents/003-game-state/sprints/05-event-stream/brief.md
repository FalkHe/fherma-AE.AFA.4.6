---
author: sprint
owner: human
created: 2026-09-16
stage: approved
---
# Sprint 05: an append-only, ordered, filterable transcript

## Outcome
The transcript is append-only, ordered and filterable: events written to a campaign run read back in write order by
id alone, a DM-visibility event is absent from the player read while still present in the table, an unknown type or
visibility is refused, and per-turn and per-run cost are exact sums over the rows.

## Acceptance criteria
*Each AC is a `@pytest.mark.database` test over `playthrough_db` (sprint 01's shared fixture): green under `make backend-test-db`, skipped under `make backend-test` (← D15).*
- AC1: inserting several events without timestamps of their own and selecting `ORDER BY id` returns them in the order they were written — the ULID primary key is the ordering, and there is no sequence column.
- AC2: `SELECT … WHERE campaign_run_id = ? AND visibility = 'player' ORDER BY id` omits a `dm` event written between two player events, and returns the two with no gap or placeholder, while the `dm` row is still there on an unfiltered read (← D4).
- AC3: `type` accepts exactly `narration`, `player_action`, `roll`, `tool_call`, `error` and raises on anything else; `visibility` accepts exactly `player` and `dm`.
- AC4: `cost_usd` is `NUMERIC(12,6)`: inserting three costs and summing them returns the exact decimal total, and `SUM` grouped by `turn_id` gives the per-turn figure — no total is stored anywhere (← D4).
- AC5: `actor_member_id` is nullable, accepts a member id, and is set to NULL rather than cascading when that member row is deleted, while `campaign_run_id` cascades; `alembic downgrade -1` drops this table and leaves the earlier ones intact, and `make backend-test`, `make backend-test-db` and `make lint` all pass.

## Decisions
← D4, D5, D9, D10, D14, D15

## Assumptions
- Adds one migration revision on top of **sprint 02's `0003`** — `0006` if it merges after 03 and 04, an earlier number if it merges first. It edits no existing revision, which is why it can run in parallel with 03 and 04.
- Carries assumptions 11 (no `adventure_run_id` on an event — the stream is one thread, ← D5), 12 (the five `type` values), 13 (`actor_member_id`) and 14 (free-form JSONB `payload`) of `decisions/model.md`.

## Out of scope
No service, route, HTTP surface or SSE, and nothing writes an event — the append path, visibility filtering and cost accounting are phase 5 · no journal entries, which belong to roadmap phase 6 · no cost display, which is a later phase and is never player-facing (← D4).
