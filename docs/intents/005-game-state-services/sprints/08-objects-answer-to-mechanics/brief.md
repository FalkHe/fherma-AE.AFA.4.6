---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 08: the world's objects answer to the mechanics and to nothing else

## Task
Implement the object and inventory mechanics over the landed `objects` rows: `interact` against a fixture's authored checks (roll or `bypassed_by`), `take`/`drop`/`give` between scene and carrier, the one-action-per-turn rule, and the `use_item` seam. Prove them against `greenhollow`'s fixtures and items.

## Outcome
`interact` applies a `FixtureCheck` by its `action` — passing on a roll ≥ `dc` or, with no roll, on a carried item in
`bypassed_by` — and `take`, `drop`, `give` move an item between a scene and a carrier only while both stand in one
scene, each recorded as a `tool_call`; a second action by the same creature in one turn is refused, and `use_item`
exists and refuses every template, none being consumable yet.

## Acceptance criteria
*All ACs are `@pytest.mark.database` tests over a started `greenhollow/v1` run positioned in `lair-maw` / `village-green`.*
- AC1: `interact(actor, thorn-screen, action, roll_id?)` passes with an `ability_check` roll `≥ dc`, passes with no roll when the actor carries an item in `bypassed_by`, is refused with an unknown `action`, a missing roll, or a roll of another `kind`; every outcome is a `tool_call` (`refused` at `dm`, ← D11) and no `objects` row changes.
- AC2: `take(actor, bent-horseshoe)` sets `owner_object_id` and clears the position; `drop` reverses it into the actor's scene; `give(from, to, item)` re-owns it; any of the three across two scenes, or on a carried-by-someone-else item, is refused.
- AC3: a second `interact`/`take`/`give`/`use_item` by the same creature within one `turn_id` is refused (count of that creature's `tool_call` events, ← D7); a new `turn_id` allows it again.
- AC4: `use_item(actor, item, target?)` exists, refuses every current template with a code that says "not consumable", and is documented as the seam.

## Decisions
← D1, D2, D7, D11

## Assumptions
- `FixtureCheck.action` text is the check's identity; `success` stays prose, no fixture state flips.
- `state` is reassigned whole (← research §C1); phase 5 writes no `state` key here.
- The one-action count treats `interact`, `take`, `drop`, `give`, `use_item`, `attack` as actions; `use_exit`, checks and rolls are free.

## Out of scope
No `reveal`, `set_state`, `create_object`, `set_hp` · scene secrets stay prose remembered by phase 6 · no encumbrance, stacking or containers beyond `owner_object_id` · no route.
