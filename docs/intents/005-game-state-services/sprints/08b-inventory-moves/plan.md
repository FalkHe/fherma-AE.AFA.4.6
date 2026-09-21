---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 08b

`research.md` covers both halves of split sprint 08; 08a is merged and its action rule is reused unchanged.
In scope: the three inventory moves, looting a container, and the `use_item` seam.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Items moving between floor, pack and container: picking one up, putting it down, handing it over — only between things in one scene — plus a placeholder for using an item that refuses everything, nothing being consumable yet | AC2, AC4, AC5: each move and its reverse; across two scenes refused; an item held by another creature refused; the sack looted; every use refused | – |
| 2 | backend-python | The module docs describe the three moves, what may be looted, and the seam | AC2, AC4, AC5 | I1–I4 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I4 |

## Interfaces
- I1 `take(user_id, actor_id, item_id)`, `drop(user_id, actor_id, item_id)`, `give(user_id, from_id, to_id, item_id)`, `use_item(user_id, actor_id, item_id, target_id=None)` — all `async`, `db` first, rest keyword-only, ending `turn_id: str | None = None`; the movers return `None`, `use_item` always raises.
- I2 The gate order 08a established, unchanged: resolve the actor and its run → **the one-action check** → the mechanic's own checks → the write → a `tool_call` `ok` → one commit. Every refusal is a `refused` `tool_call` at `dm`, committed alone, then raised (← D11). `take`, `give` and `use_item` spend the turn's action; **`drop` does not** — the product owner ruled dropping free, following the SRD.
- I3 What each move does to the row: `take` sets `owner_object_id` to the actor and clears the position; `drop` clears the owner and puts the item in the actor's scene and adventure run; `give` re-owns it from one carrier to another. Recorded `args`: `take`/`drop` `{actorId, itemId}`, `give` `{actorId, toId, itemId}` — the giver is `actorId`, so one key always names the actor. `outcome` is `{}`.
- I4 Reachability, and the one widening this sprint makes (AC5): an item may be taken when it lies in the actor's own scene, **or** when its owner is a non-creature object standing in that scene — so `stolen-fleece` comes out of `wool-sack`. An item held by *another creature* stays refused, as does anything in another scene, and an actor standing nowhere. `give` requires both creatures in one scene. The refusal is `OBJECT_NOT_REACHABLE` (new, 409). `use_item` refuses every template with `ITEM_NOT_CONSUMABLE` (new, 409): an item template carries no consumable field today, so a later field plus a branch **before** that refusal is purely additive.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_inventory_moves.py`, all `@pytest.mark.database` over a started `greenhollow/v1` run.
- AC2 → take, drop and give each move the item; across two scenes, and an item held by another creature, refused.
- AC5 → the fleeces come out of the wool sack; a creature's own held item still cannot be taken from it.
- AC4 → using any item is refused as not consumable, and nothing moves.

## Order
Parallel: WI1, WI2, qa.

## Note
Each scenario mints its own `turn_id`: one action per creature per turn is enforced now, and `take` → `give` is
two actions. `drop` being free is what lets take-then-drop run inside one turn.
