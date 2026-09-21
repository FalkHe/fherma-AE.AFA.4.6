---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 07a

`research.md` covers both halves of split sprint 07. In scope: dice, derivation, the producers, `ask_player`,
the command, the authoring floor. Consumption and `awaiting` are 07b.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Dice the server rolls itself, and a formula worked out from the kind of roll and who is rolling — never from a number anybody passed in | AC1: each kind's derivation; a malformed expression named in its own error; the generator replaced in tests | – |
| 2 | backend-python | Asking a player to roll, answering that request, rolling outright, a passive check, and asking a question — each recorded as its own kind of entry | AC2, AC4a: the request and its answer; faces, modifier, total; a hidden roll; a passive check with no faces; a question | WI1, I1–I5 |
| 3 | backend-python | Authored content below the SRD's own difficulty floor is refused, and the guide says so | AC5: under 5 refused, 5 and above accepted; Greenhollow still validates | – |
| 4 | backend-python | Rolling from the command line shows the working: kind, actor, formula, dice, total | AC4a: the printed derivation; a bad `custom` expression naming itself | WI2, I1–I5 |
| 5 | backend-python | The module docs describe how a roll is derived and recorded; the content guide, the new floor | AC1, AC2, AC5 | I1–I5 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I5 |

## Interfaces
- I1 `dice.roll(expression) -> DiceRoll{faces, modifier, total}` parsing `NdM±K`, rolling behind `dice._rng() -> random.Random`; anything else raises `InvalidDiceExpressionError` naming the expression (`VALIDATION_ERROR`). Cap an expression at 20 dice of at most 100 faces.
- I2 `derive_formula(kind, actor, context, *, campaign_id, version) -> str`: item `to_hit` for `attack`, item `damage` for `damage`, the ability modifier for `ability_check` and `saving_throw`, Dexterity for `initiative`, the explicit expression for `custom`. An attack comes from `context.item_id`'s template when one is given, otherwise from the actor's own stat block, chosen **by name** — a monster with two attacks is disambiguated by the DM naming one, never by position.
- I3 Producers — each `async`, `db` first, rest keyword-only, each taking `turn_id: str | None = None` (phase 8 passes a real one; today everything lands in the untagged turn), each resolving its run from the id it is given and then following `use_exit`'s gate order:

  | Function | Appends |
  |---|---|
  | `request_player_roll(user_id, actor_id, kind, context) -> Event` | `roll_requested {kind, actorId, formula, context}`; its own id is the request id |
  | `resolve_roll_request(user_id, request_id) -> Event` | `roll {requestId, kind, faces[], modifier, total}`, re-using the request's stored `formula`, `kind`, `actor_id` and `visibility` |
  | `roll(user_id, actor_id, kind, context, visibility="dm") -> Event` | both of the above at once |
  | `passive_check(user_id, actor_id, ability, dc) -> bool` | a `tool_call` at `dm` — **not** a `roll`: it has no faces and must never be consumable |
  | `ask_player(user_id, run_id, text, options)` | `question` |

- I4 **"Never a number a caller passed" is structural** (← D6): no producer takes `formula`, `modifier`, `bonus`, `faces` or `total` — there is no parameter to pass one through. The only caller numbers are `dc` (07b) and `expression`, reachable only under `kind="custom"`.
- I5 Content: `FixtureCheck.dc` and `Secret.dc` become `ge=5, le=30`, matching the SRD's own table and D6. Greenhollow's authored checks are 8, 10, 12, 12, 13 and 14, so nothing shipped breaks.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_rolls_derived_and_recorded.py`; database-touching tests carry `@pytest.mark.database`.
- AC1 → every kind derives from actor and kind alone; a malformed expression names itself.
- AC2 → the request and its answer, the outright roll, the hidden one, the passive check without faces.
- AC4a → a question is recorded; the command prints the derivation and the result.
- AC5 → content below the floor refused, at the floor accepted, Greenhollow still valid.

## Order
Parallel: WI1, WI3, WI5, qa. Then: WI2. Then: WI4.
