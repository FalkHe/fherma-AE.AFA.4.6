---
author: sprint
owner: human
created: 2026-09-21
stage: approved
---
# Sprint 08b: items move between the floor, a pack and a container

Half of the approved sprint 08, split on the precedent set for sprints 05, 06 and 07. The other half is 08a,
which must land first. Task, outcome and criteria are that brief's, partitioned — with one addition the product
owner made mid-sprint, marked AC5.

## Task
Implement `take`/`drop`/`give` between scene, carrier and container, and the `use_item` seam.

## Outcome
`take`, `drop` and `give` move an item between a scene and a carrier only while both stand in one scene, each
recorded as a `tool_call`, and `use_item` exists and refuses every template, none being consumable yet.

## Acceptance criteria
*All ACs are `@pytest.mark.database` tests over a started `greenhollow/v1` run.*
- AC2: `take(actor, bent-horseshoe)` sets `owner_object_id` and clears the position; `drop` reverses it into the actor's scene; `give(from, to, item)` re-owns it; any of the three across two scenes, or on an item carried by someone else, is refused.
- AC4: `use_item(actor, item, target?)` exists, refuses every current template with a code that says "not consumable", and is documented as the seam.
- AC5: a container standing in the actor's scene can be looted — `take` accepts an item whose owner is a non-creature object in that scene, so `stolen-fleece` comes out of `wool-sack`; taking from a creature other than the actor stays refused.

## Decisions
← D1, D2, D7, D11 · the product owner's mid-sprint rulings: **a container in the scene can be looted** (AC5), and **dropping is free**, so it does not spend the turn's action.

## Assumptions
- `state` is reassigned whole (← research §C1); phase 5 writes no `state` key here.
- The action count landed in 08a and is reused unchanged: `take`, `give` and `use_item` are actions; `drop` is free.
- Each test scenario mints its own `turn_id`, since one action per creature per turn is now enforced.

## Out of scope
`interact` and the action count itself — both 08a · no encumbrance, stacking or nesting beyond one `owner_object_id` hop · no route.
