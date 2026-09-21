---
author: sprint
owner: human
created: 2026-09-21
stage: approved
---
# Sprint 07a: a roll is derived by the server and recorded as it fell

Half of the approved sprint 07, split on the precedent set for sprints 05 and 06: one sprint carried a dice
module, derivation for six kinds, four roll-producing functions, a consumption rule, a wire-shape change and a
command. The other half is 07b. Task, outcome and criteria are that brief's, partitioned — with one addition the
product owner decided mid-sprint, marked AC5.

## Task
Implement dice and the first half of the roll contract: the dice module behind an RNG seam, server-side formula derivation by `kind` + actor, the `roll_requested` → `roll` event pair, hidden and passive rolls, `ask_player`, and the `app playthrough roll` one-off.

## Outcome
`request_player_roll` appends `roll_requested` with the formula derived from `kind` + actor — never a number a caller
passed — `resolve_roll_request` answers it with a `roll` event carrying faces, modifier and total, and
`app playthrough roll` shows the same derivation, a bad `custom` expression naming itself.

## Acceptance criteria
- AC1: `playthrough/dice.py` parses `NdM±K` and rolls through an `_rng()` seam; `derive_formula(kind, actor, context)` yields item `to_hit` for `attack`, item `damage` for `damage`, the ability modifier for `ability_check`/`saving_throw`, Dexterity for `initiative`, the explicit expression for `custom`; a malformed expression raises an error naming the expression (unit tests, `_rng` monkeypatched).
- AC2 (`@pytest.mark.database`): `request_player_roll` appends `roll_requested {kind, actorId, formula, context}`; `resolve_roll_request(request_id)` appends `roll {requestId, kind, faces[], modifier, total}` at the request's visibility; `roll(...)` does both at once; `passive_check` appends a `dm` event with no faces.
- AC4a: `ask_player` appends `question`; `app playthrough roll <kind> --actor <id>` prints the derivation and result (`CliRunner`).
- AC5: the authored difficulty floor matches the rules — content refuses a difficulty below 5, as the SRD's own table and D6 both have it; the authoring guide says so; nothing shipped breaks.

## Decisions
← D1, D5, D6, D9, D13 · the product owner's mid-sprint rulings: the SRD's table binds authoring too, and a monster's attack is chosen by the DM by name and derived from its stat block.

## Assumptions
- No dice dependency: stdlib `random`; `dice` 4.0.0 and `d20` 1.1.2 rejected (research §D).
- Advantage/disadvantage are not authored and not built.
- `passive_check` records a `tool_call` at `dm`, not a `roll` — it has no faces and must not be consumable.

## Out of scope
Single consumption, the check/save consumers and `awaiting` — all 07b · no `POST …/roll/{requestId}` route, no graph interrupt (← D10, D14, phase 8) · no seed column (← D13) · no `interact`/`attack` consumers (08, 09).
