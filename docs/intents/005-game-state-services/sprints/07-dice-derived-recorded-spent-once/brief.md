---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 07: a roll is derived by the server, recorded as it fell, and spent once

## Task
Implement dice and the roll-result contract: the dice module behind an RNG seam, server-side formula derivation by `kind` + actor, the `roll_requested` → `roll` event pair, hidden and passive rolls, `ask_player`, the check/save consumers, single consumption of a roll, the `awaiting` derivation and the `app playthrough roll` one-off.

## Outcome
`request_player_roll` appends `roll_requested` with the formula derived from `kind` + actor (never a number a caller
passed), `resolve_roll_request` answers it with a `roll` event carrying faces, modifier and total, `resolve_check` /
`resolve_save` turn that roll id into pass/fail on their own `tool_call` event, and the same roll id used twice, in a
later turn, or of the wrong `kind` is refused — with `app playthrough roll` showing the same derivation and a bad
`custom` expression naming itself.

## Acceptance criteria
- AC1: `playthrough/dice.py` parses `NdM±K` and rolls through an `_rng()` seam; `derive_formula(kind, actor, context)` yields item `to_hit` for `attack`, item `damage` for `damage`, the ability modifier for `ability_check`/`saving_throw`, Dexterity for `initiative`, the explicit expression for `custom`; a malformed expression raises an error naming the expression (unit tests, `_rng` monkeypatched).
- AC2 (`@pytest.mark.database`): `request_player_roll` appends `roll_requested {kind, actorId, formula, context}`; `resolve_roll_request(request_id)` appends `roll {requestId, kind, faces[], modifier, total}` at the request's visibility; `roll(...)` does both at once; `passive_check` appends a `dm` event with no faces.
- AC3 (`@pytest.mark.database`): `resolve_check(roll_id, dc)` / `resolve_save` append a `tool_call` with `rollIds:[id]` and `outcome.success`; the same `roll_id` a second time, from another `turn_id`, or of another `kind`, and a `dc` outside 5–30, are refused and recorded `refused` at `dm` (← D11); a `custom` roll is refused by every check.
- AC4: `ask_player` appends `question`; `get_awaiting(run)` returns `none | roll:<id> | answer:<id>` from the open turn's events and is added to the `GET …/events` response; `app playthrough roll <kind> --actor <id>` prints the derivation and result (`CliRunner`).

## Decisions
← D1, D5, D6, D9, D11, D13

## Assumptions
- No dice dependency: stdlib `random`; `dice` 4.0.0 and `d20` 1.1.2 rejected (research §D).
- `_consume_roll(...)` and `_acted_this_turn(...)` are private helpers shared with 08/09; both scan the open `turn_id` on `ix_events_campaign_run_id_turn_id`.
- Advantage/disadvantage are not authored and not built.

## Out of scope
No `POST …/roll/{requestId}` route, no graph interrupt (← D10, D14, phase 8) · no seed column: replay reads the stored faces (← D13) · no `interact`/`attack` consumers (08, 09).
