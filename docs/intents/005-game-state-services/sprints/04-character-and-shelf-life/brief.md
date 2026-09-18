---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 04: the run gets its character and becomes playable

## Task
Implement the second lifecycle step and the run's shelf life: create the player character from the seed sheet as the only caller of the generic object write, carry its inventory as real items, move the run to `ready`; add rename, archive and unarchive with archived runs read-only. Correct the general docs that still describe run start and character creation as one step.

## Outcome
`POST …/character` creates one creature owned by the member with no `template_id`, carrying the seed inventory as real
item rows, and moves the run `setup → ready`; the run can be renamed, archived and unarchived, an archived run still
lists and reads but refuses that same write, and a second character on a `ready` run is refused.

## Acceptance criteria
- AC1: `POST /api/v1/playthrough/campaign/{id}/character` on a `setup` run answers 201 with the character (`id, name, currentHp, maxHp, armourClass`) and the run reads `status: "ready"`; a second call answers the envelope with a domain code.
- AC2 (`@pytest.mark.database`): the character row has `member_id` set, `template_id NULL`, `instance_key pc:<member_id>:1`, `current_hp == max_hp`, `armour_class` and abilities from the seed; one carried `item` row per seed inventory entry with `owner_object_id` = the character and no position.
- AC3: `PATCH …/campaign/{id} {title}` renames; `POST …/archive` and `…/unarchive` flip `active|ready ↔ archived`; on an archived run `GET` list/read still answer while `PATCH`, `…/character` and `…/adventure` answer a `RUN_ARCHIVED`-class code (← D12).
- AC4: `activate_campaign_run(ready → active)` exists as a service function with a unit test and no route; `docs/general/model.md:311`-`312` split "start a run" and "create the character" (← research §C6); docs updated.

## Decisions
← D1, D2, D3, D4, D12 · research §C6

## Assumptions
- `create_character(db, *, user_id, run_id, sheet)` takes a `SeedCharacter`-shaped sheet, read from the pinned campaign until phase 7 supplies it — the signature does not change then.
- Refusing a second character is a Stage-01 gameplay rule in the service (003 §3.6's "raise, never guess"), not a schema constraint (← 003-D13).
- `state` JSONB is written whole from a per-kind Pydantic model (`playthrough/schemas.py`).

## Out of scope
No generation chat, graph or UI (← D4, phase 7) · no ability rolling, no portrait · `active` is set by phase 8's intro · no delete route, ever.
