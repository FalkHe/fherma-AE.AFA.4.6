---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 01

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Hidden facts and fixture checks carry a required ability and optional skill (I1); the six Greenhollow entries are filled; the content doc and existing test fixtures build valid content | a secret or fixture check without `ability` is refused by the model; `app content validate` fails on a tree missing it; shipped Greenhollow validates | – |
| 2 | backend-python | One playthrough helper turns an authored secret or fixture check into the `(ability, skill, dc)` triple the existing check, save and roll-request entry points accept (I2); `passive_check` accepts an optional `skill` and records it; every current signature is unchanged so the old tools keep working | active check, passive check and save built from an authored entry use the authored ability in the derived formula; no existing game test changes behaviour | I1 field names |

## Interfaces
- I1 (content/schemas.py, both models gain exactly these fields; JSON keys snake_case):
  ```python
  AbilityName = Literal["strength","dexterity","constitution","intelligence","wisdom","charisma"]
  class FixtureCheck(ContentModel):
      action: ProseText
      ability: AbilityName          # required
      skill: ProseText | None = None
      dc: int = Field(ge=5, le=30)
      success: ProseText
      bypassed_by: list[ContentId] = Field(default_factory=list)
  class Secret(ContentModel):
      fact: ProseText
      ability: AbilityName          # required
      skill: ProseText | None = None
      dc: int = Field(ge=5, le=30)
      discovered_by: ProseText      # unchanged, narration guidance only
  ```
- I2 (playthrough, unchanged signatures WI2 builds on; `skill` is the only addition):
  ```python
  dice.derive_formula(kind, actor, context, *, campaign_id, version, item=None) -> str   # context={"ability": AbilityName}
  service.passive_check(db, *, user_id, actor_id, ability, dc, turn_id=None, skill=None) -> bool
  service.resolve_check(db, *, user_id, roll_id, dc, turn_id=None) -> bool
  service.resolve_save(db, *, user_id, roll_id, dc, turn_id=None) -> bool
  service.request_player_roll(db, *, user_id, actor_id, kind, context, turn_id=None) -> Event
  ```
  New helper: `service.authored_check(entry: Secret | FixtureCheck) -> tuple[AbilityName, str | None, int]`.

## Acceptance tests (qa)
No qa agent: owner asked to reduce testing; WI tests cover AC1–AC3 directly, AC4 is the unchanged full suite.

## Order
Parallel: WI1, WI2 (WI2 constructs I1 models in its own fixtures; merge order WI1 then WI2).
