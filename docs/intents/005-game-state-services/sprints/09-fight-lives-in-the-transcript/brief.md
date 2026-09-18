---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 09: a fight happens entirely in the transcript

## Task
Implement events-only combat: `attack` against the target's AC, `damage` bound to its hit, `is_alive`/`down` at zero, and `roll_initiative` as two recorded rolls — and prove that nothing anywhere stores that a fight is happening.

## Outcome
`attack` compares an `attack` roll against the target's `armour_class` and records hit, miss or crit, `damage` applies
its own roll to that hit id, clamping at `0` and turning a member-less creature `is_alive=false` while a character gets
`down`, `roll_initiative` writes one `roll` per side and stores nothing else, and no table, column or row anywhere
records that a fight is happening.

## Acceptance criteria
*All ACs are `@pytest.mark.database` tests over a started run with the character and a `goblin` (AC 13, 7 hp) in one scene; `_rng` pinned.*
- AC1: `attack(actor, target, item, roll_id)` with an `attack` roll appends a `tool_call` with `outcome ∈ hit|miss|crit` (crit on a natural 20 regardless of AC); `total ≥ armour_class` hits; pass/fail is on the `tool_call`, never on the `roll` (← D11); a target in another scene, an item the actor does not carry, or a non-`attack` roll is refused.
- AC2: `damage(target, roll_id, hit_id)` with a `damage` roll and a `hit_id` naming an `attack` `tool_call` of the same turn with `outcome hit|crit` lowers `current_hp`, clamped at 0; at 0 a member-less creature gets `is_alive=false`, a character keeps `is_alive=true` and gets `state.down=true`; a `hit_id` from another turn, already damaged, or a miss is refused.
- AC3: a second `attack` by the same creature in one `turn_id` is refused; a creature attack (`roll` + `attack` + `damage`) completes with no `roll_requested`.
- AC4: `roll_initiative(side_a, side_b)` appends exactly two `roll(initiative)` events and changes no row; a schema-wide assertion shows no table, column or `state` key names an encounter, turn order or `in_combat`.

## Decisions
← D1, D2, D6, D7, D11

## Assumptions
- `damage` reads its target from the `attack` event named by `hit_id` and refuses a mismatching `target_id` argument.
- Death is `is_alive=false` and nothing else — no corpse, loot or inventory transfer.
- `roll_initiative` requests the player's die through `request_player_roll` when a side contains a character; the test resolves it directly.

## Out of scope
No encounter row, turn pointer, `in_combat` flag or stored order (← D7, 003-D8) · no conditions beyond `down` · no healing, rest or resurrection · no spells (none authored) · no route.
