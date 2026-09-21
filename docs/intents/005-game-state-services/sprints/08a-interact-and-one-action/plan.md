---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 08a

`research.md` covers both halves of split sprint 08. In scope: `interact` and the one-action-per-turn rule.
The inventory moves and the `use_item` seam are 08b.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Interacting with a fixture by the action its author wrote: passing on a good enough roll, or with no roll when the actor carries the thing that gets past it — refusing anything else without changing the world | AC1: the roll path, the bypass path, an unknown action, a missing roll, a wrong-kind roll; all recorded, refusals for the DM only; no object row changes | – |
| 2 | backend-python | One action per creature per turn, shared by every acting mechanic | AC3: a second action refused; a new turn allows it; a refusal does not spend the turn; rolls and exits do not count | WI1, I1–I5 |
| 3 | backend-python | The module docs describe interacting and the action rule, and that dropping is free | AC1, AC3 | I1–I5 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I5 |

## Interfaces
- I1 `interact(user_id, actor_id, object_id, action, roll_id=None) -> bool`, `async`, `db` first, rest keyword-only, ending `turn_id: str | None = None`. Gate order, which every acting mechanic shares: resolve the actor and its run → the one-action check → the mechanic's own checks → the write → a `tool_call` `ok` → one commit. Every refusal is a `refused` `tool_call` at `dm`, committed alone, then raised (← D11).
- I2 Recorded `args {actorId, objectId, action, rollId?}`; on success `outcome {action, dc, total?, bypassedBy?, success}`; `rollIds` is `[roll_id]` for a roll-fed interact, else `[]`. A roll is consumed through 07b's helper, never a second implementation — so a wrong-kind or spent roll stays `ROLL_NOT_USABLE`.
- I3 **Bypass**: a row with `owner_object_id = actor.id` and `template_id` in the check's `bypassed_by`, consulted **only** when no roll was given; the matching id is reported as `outcome.bypassedBy`. `action` matches by exact string equality — phase 8's tool layer offers the authored strings verbatim.
- I4 **One action per turn**: this run's `tool_call` events where the turn `IS NOT DISTINCT FROM` the call's, with `result == "ok"`, `name` in `{interact, take, give, use_item, attack}` and `args["actorId"]` the actor. **`drop` is not in that set** — the product owner ruled dropping free, as the SRD and `decisions/mechanics.md` both have it, superseding the brief's own list. `use_exit`, rolls and checks are free, and a refusal never spends the turn. `attack` is in the set already so that sprint 09 needs no edit here.
- I5 New codes, all 409: `ACTION_NOT_AVAILABLE` (unknown action, or no fixture), `ROLL_REQUIRED` (a check needing a roll, none given and nothing bypassing), `ALREADY_ACTED`. An unknown id stays `NOT_FOUND`.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_interact_and_one_action.py`, all `@pytest.mark.database` over a started `greenhollow/v1` run.
- AC1 → the roll path, the bypass path, the three refusals; nothing changes on a refusal.
- AC3 → a second action refused, a new turn allowing it, a refusal not spending the turn.

## Order
Parallel: WI1, WI3, qa. Then: WI2.

## Note
With no turn allocator yet every mechanic lands in one untagged turn, so each scenario must mint its own
`turn_id` or a creature's second action in the whole run is refused.
