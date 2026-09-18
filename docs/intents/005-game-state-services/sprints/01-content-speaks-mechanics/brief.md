---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 01: the content speaks the mechanics' language

## Task
Check the existing `greenhollow` adventure and the content schema against the new mechanics and correct both where they fall short: an exit must be addressable by id and able to end the adventure (`use_exit`), and the seed character's inventory must be real item templates so `attack` can name a weapon. Restate the loader rules the change breaks, edit the shipped content, and keep `app content validate` green.

## Outcome
`app content validate` still passes `greenhollow` after `lair-hollow` gains an exit that ends the adventure — an
`adventure_end` exit carries no `to` and satisfies the terminal-scene rule, a `scene` exit without `to` is refused, two
exits sharing an id in one scene are refused — and the seed character's inventory names item templates, so an unknown or
non-item entry is refused.

## Acceptance criteria
- AC1: `Exit` gains `id: ContentId` and `kind: Literal["scene","adventure_end"] = "scene"`; `to` is required for `scene` and must be absent for `adventure_end` (`tests/content/test_schemas.py`).
- AC2: the terminal-scene rule (R9/R10) reads "reachable and ends in an `adventure_end` exit" instead of `exits == []`; `lair-hollow` with one `adventure_end` exit passes, a scene with no exits at all is refused (`tests/content/test_service.py`).
- AC3: two exits with one id in one scene are refused with a tag naming scene and id (new R19); `SeedCharacter.inventory: list[ContentId]` entries must name an `item` template and count as R14 references (new R20).
- AC4: `greenhollow/v1` carries the ending exit and template ids in the seed inventory (the missing items become `item` templates); `app content validate` and `make test` pass; `docs/modules/content.md` rule table and scene section describe R19/R20 and `Exit.kind`.

## Decisions
← D8 · research §B1, §B2

## Assumptions
- `greenhollow/v1` is edited in place, not cut as `v2`: 003-D7 pins existing runs and none exists yet.
- `Exit.id` is needed because `use_exit(actor_id, exit_id)` must address an `adventure_end` exit, which has no `to`.
- `shepherds-knife` moves into the seed inventory; `wooden-shield`, `hooded-lantern`, `coil-of-twine`, `rations` become item templates so R14 stays satisfied.

## Out of scope
No `playthrough` code · no new scenes, secrets or prose beyond the one ending exit and four item templates · `Exit.condition` and `FixtureCheck.success` stay prose, DM judgment (← D8).
