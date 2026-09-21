---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 09

Not split — the three mechanics reuse the gate order, the roll consumption and the one-action helper unchanged,
and splitting would cut damage from the attack entry it binds to. Last sprint of the intent.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Striking at somebody and hurting them: a swing measured against the target's armour, and a wound bound to the swing that landed it — nothing hurt without a hit behind it | AC1–AC3: hit, miss, a natural 20; a target elsewhere, an unheld weapon, a wrong roll refused; damage clamped at nothing, a monster killed, a character left down; a hit spent twice, from another turn, or on a miss refused | – |
| 2 | backend-python | Rolling for who goes first, recording two rolls and changing nothing — and proof that nowhere in the database is there such a thing as a fight in progress | AC4: two initiative rolls, no row touched; the tables, the object and event columns, and every key stored in a state, each an exact set | WI1, I1–I4 |
| 3 | backend-python | The module docs describe a fight as something that happens entirely in the transcript | AC1–AC4 | I1–I4 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I4 |

## Interfaces
- I1 `attack(user_id, actor_id, target_id, item_id=None, roll_id) -> "hit" | "miss" | "crit"`. `item_id` is optional — a monster's attack comes from its stat block, not an item. Order: the shared gate → the one-action check → load target and item → both in one scene → the item carried by the actor → consume an `attack` roll. **Crit iff the die came up a natural 20**, legible because a roll records its individual dice and an attack formula is always one d20; otherwise a hit iff the total reaches the target's armour class. Writes no row. Records `args {actorId, targetId, itemId?, rollId}`, `rollIds [roll_id]`, `outcome {outcome, total, natural, armourClass}`.
- I2 `damage(user_id, target_id, roll_id, hit_id) -> int`, the hit points applied. `hit_id` names an **attack entry by its event id**, refused unless that entry is in the same run, is an `attack`, succeeded, landed (a miss fails here), belongs to this turn, and has not already been damaged this turn. **The target is read from that entry, never from the argument**, which must match it. Then a `damage` roll is consumed and `min(total, current_hp)` applied. At zero a creature with no member becomes not alive; a character stays alive, its state reassigned whole with `down`. Records `args {targetId, rollId, hitId}`, `outcome {rolled, applied, currentHp, isAlive, down}`. New code `HIT_NOT_USABLE` (409).
- I3 `roll_initiative(user_id, side_a_ids, side_b_ids) -> tuple[Event, Event]`: per side, a row belonging to a member is asked to roll, otherwise it is rolled outright at `player` visibility. No row written, no `tool_call`.
- I4 Refusals reuse the existing codes — `ALREADY_ACTED`, `OBJECT_NOT_REACHABLE`, `ROLL_NOT_USABLE` — each recorded as a `refused` `tool_call` at `dm` and committed before raising. Unknown or foreign ids stay `NOT_FOUND` and are **not** recorded (← D12).

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_fight_in_the_transcript.py`, all `@pytest.mark.database` over a run with the character and a goblin in one scene, the dice pinned.
- AC1 → hit, miss, natural-20 crit; the three refusals; pass or fail never on the roll.
- AC2 → hit points fall and clamp at nothing; the goblin dies, the character goes down; a hit spent twice, from another turn, or on a miss refused.
- AC3 → a second attack in one turn refused; a monster's attack needs no request to the player.
- AC4 → two initiative rolls, nothing written; nowhere a fight, a turn order or a combat flag.

## Order
Parallel: WI1, WI3, qa. Then: WI2.
