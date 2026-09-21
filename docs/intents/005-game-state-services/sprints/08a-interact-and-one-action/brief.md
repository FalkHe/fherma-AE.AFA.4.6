---
author: sprint
owner: human
created: 2026-09-21
stage: approved
---
# Sprint 08a: a fixture is interacted with, and a creature acts once a turn

Half of the approved sprint 08, split on the precedent set for sprints 05, 06 and 07. The other half is 08b.
Task, outcome and criteria are that brief's, partitioned — with one correction the product owner made mid-sprint.

## Task
Implement `interact` against a fixture's authored checks (roll or `bypassed_by`), and the one-action-per-turn rule every acting mechanic shares. Prove them against `greenhollow`'s fixtures.

## Outcome
`interact` applies a `FixtureCheck` by its `action` — passing on a roll ≥ `dc` or, with no roll, on a carried item in
`bypassed_by` — and a second action by the same creature in one turn is refused.

## Acceptance criteria
*Both ACs are `@pytest.mark.database` tests over a started `greenhollow/v1` run positioned in `lair-maw` / `village-green`.*
- AC1: `interact(actor, thorn-screen, action, roll_id?)` passes with an `ability_check` roll `≥ dc`, passes with no roll when the actor carries an item in `bypassed_by`, is refused with an unknown `action`, a missing roll, or a roll of another `kind`; every outcome is a `tool_call` (`refused` at `dm`, ← D11) and no `objects` row changes.
- AC3: a second action by the same creature within one `turn_id` is refused (count of that creature's `tool_call` events, ← D7); a new `turn_id` allows it again.

## Decisions
← D1, D2, D7, D11 · the product owner's mid-sprint correction: **dropping an item is free**, as the SRD and `decisions/mechanics.md` both have it, so the brief's own list is superseded.

## Assumptions
- `FixtureCheck.action` text is the check's identity; `success` stays prose, no fixture state flips.
- The one-action count treats `interact`, `take`, `give`, `use_item` and `attack` as actions; `drop`, `use_exit`, checks and rolls are free.
- With no turn allocator yet, every mechanic lands in the single untagged turn, so each test scenario mints its own `turn_id`.

## Out of scope
`take`/`drop`/`give` and the `use_item` seam — all 08b · no `reveal`, `set_state`, `create_object`, `set_hp` · no fixture state flips · no route.
