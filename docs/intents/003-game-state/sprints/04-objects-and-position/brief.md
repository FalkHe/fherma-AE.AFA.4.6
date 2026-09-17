---
author: sprint
owner: human
created: 2026-09-16
stage: approved
---
# Sprint 04: objects that hold only what the content declares

## Outcome
The world's objects hold what the authored content declares and nothing it does not: a creature carries hit points and
armour class, an item attempting either is refused, hit points above the maximum are refused, a carried item cannot
also stand in a scene, a character's position names the adventure run that scopes its scene, and one member may hold
two characters.

## Acceptance criteria
*Each AC is a `@pytest.mark.database` test over `playthrough_db` (sprint 01's shared fixture): green under `make backend-test-db`, skipped under `make backend-test` (← D15).*
- AC1: `kind` accepts only `creature`, `item`, `fixture` — the discriminator the content uses (`content/schemas.py:67`-`70`) — and a `creature` row requires all four of `current_hp`, `max_hp`, `armour_class`, `is_alive`, while an `item` or `fixture` carrying any of them raises.
- AC3: `current_hp` outside `0 .. max_hp` raises; at `current_hp = 0` both `is_alive` values are accepted (stable is not dead).
- AC4: a row with `owner_object_id` set and a position raises; `adventure_run_id` and `scene_id` must be both set or both NULL; a row with neither owner nor position inserts — it belongs to an adventure nobody has entered (← D12).
- AC5: two `objects` rows with `member_id` pointing at the same member **insert** — no unique index restricts the count (← D13); the same `instance_key` twice in one campaign run raises; `alembic downgrade -1` drops this table and leaves 02's and 03's intact, and `make backend-test`, `make backend-test-db` and `make lint` all pass.

## Decisions
← D8, D9, D10, D12, D13, D14, D15

## Assumptions
- Adds migration revision `0005` on top of sprint 03's `0004` and edits neither. Carries assumptions 3 (the position/carried check), 8 (`is_alive` stored, not derived), 9 (the `instance_key` format, `pc:<member_id>:<n>` for a character) and 10 (`name` copied onto the row) of `decisions/model.md`.
- Provenance (`source_adventure_id`, `source_scene_id`) is distinct from position, because objects exist before their adventure is entered.

## Out of scope
No service, route or HTTP surface, and **nothing instantiates objects from content** — that is phase 5's run-start lifecycle · no per-`kind` Pydantic state models (they belong with the write path) · no combat state (← D8).
