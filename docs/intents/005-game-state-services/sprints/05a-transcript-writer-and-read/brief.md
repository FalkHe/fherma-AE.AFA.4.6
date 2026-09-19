---
author: sprint
owner: human
created: 2026-09-19
stage: approved
---
# Sprint 05a: the transcript records and reads back

Half of the approved sprint 05, split on the product owner's instruction because one sprint carried four
surfaces. The other half is 05b. Task, outcome and criteria are that brief's, partitioned — nothing is added.

## Task
Implement the transcript's writing and reading: the single `append_event` writer with per-type payload validation, and the player-visible events read with `after=` paging. Document the event-id ordering caveat.

## Outcome
Events appended through `append_event` read back in order from `GET …/events?after=<id>` at `player` visibility,
with a `dm` event absent from the read while still present in the table.

## Acceptance criteria
- AC1: `append_event(db, *, run_id, type, visibility, payload, turn_id=None, actor_member_id=None, usage=None)` validates `payload` against the per-type model of `playthrough/schemas.py` (shapes from `decisions/mechanics.md`) and is the only writer of `events`.
- AC2: `GET /api/v1/playthrough/campaign/{id}/events?after=<id>&limit=` returns `player` events ordered by id alone, `after` exclusive; a `dm` event written between two `player` events is absent from the response and present in the table (`@pytest.mark.database`).
- AC5: `docs/modules/playthrough.md` records the reads and the caveat that event ids order the transcript only because one process mints them.

## Decisions
← D9, D12 · research §C1, §C2

## Assumptions
- `events.id` is the chronological key; the one-process monotonicity caveat is written into `docs/modules/playthrough.md`, not fixed with a sequence.
- `payload` is stored camelCase and passed through the read unmapped.

## Out of scope
Cost and the SSE signal — both 05b · no `awaiting` derivation (07) · no `turn_id` allocation, no turn route (phase 8) · no narration written by an LLM here · no frontend.
