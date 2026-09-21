---
author: sprint
owner: human
created: 2026-09-21
stage: approved
---
# Sprint 07b: a roll is spent once, and the client sees what is awaited

Half of the approved sprint 07, split on the precedent set for sprints 05 and 06. The other half is 07a, which
must land first. Task, outcome and criteria are that brief's, partitioned — nothing is added.

## Task
Implement the consuming half of the roll contract: the check and save consumers, single consumption of a roll, and the `awaiting` derivation on the events read.

## Outcome
`resolve_check` / `resolve_save` turn a roll id into pass/fail on their own `tool_call` event, and the same roll id
used twice, in a later turn, or of the wrong `kind` is refused.

## Acceptance criteria
- AC3 (`@pytest.mark.database`): `resolve_check(roll_id, dc)` / `resolve_save` append a `tool_call` with `rollIds:[id]` and `outcome.success`; the same `roll_id` a second time, from another `turn_id`, or of another `kind`, and a `dc` outside 5–30, are refused and recorded `refused` at `dm` (← D11); a `custom` roll is refused by every check.
- AC4b: `get_awaiting(run)` returns `none | roll:<id> | answer:<id>` from the open turn's events and is added to the `GET …/events` response.

## Decisions
← D1, D5, D6, D9, D11 · research §C

## Assumptions
- `_consume_roll(...)` is a private helper shared with 08 and 09; it scans the open `turn_id` on `ix_events_campaign_run_id_turn_id`.
- `_acted_this_turn(...)` belongs to sprint 08, not here.
- With the authoring floor raised to 5 in 07a, the 5–30 rule now binds authored and DM-picked difficulties alike.

## Out of scope
Dice, derivation and the roll producers — all 07a · no turn allocation, no turn route (phase 8) · no `interact`/`attack` consumers (08, 09).
