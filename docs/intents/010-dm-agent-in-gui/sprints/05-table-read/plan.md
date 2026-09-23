---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 05

Research's WI1 and WI2 both edit the same two files, so they run in sequence rather than side by side;
regenerating the typed client is folded into the second. No qa work item — the backlog reserves acceptance
tests for sprint 03 — so each work item's own tests cover its criteria.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | One hero shape on the wire, carrying ability scores with modifiers, backstory and carried items, shared by every read that already returns a hero | a hero read carries all six abilities with signed modifiers, backstory and items; the existing reads keep working and gain the fields; carried items come from one grouped query, not one per hero | – |
| 2 | backend-python | The play screen's read: one call returning the run, its campaign, the current adventure, the current scene and every seated hero; plus the regenerated typed client | names the current adventure and the scene the hero stands in; each hero carries the full sheet; hit points reflect a wound on a second read; a caller not seated is refused | WI1, interfaces I1–I4 |

## Interfaces
- I1 — `GET /api/v1/playthrough/runs/{run_id}/table` → 200 `TableRead`; 401; 404 `NOT_FOUND` (unknown or
  foreign run, via `_require_member`). Read-only.
  ```
  TableRead        runId: string · runTitle: string|null · runStatus: string
                   campaignTitle: string|null · adventure: TableAdventure|null
                   scene: TableScene|null · heroes: CharacterRead[]
  TableAdventure   id: string (content id) · runId: string (adventure_runs.id)
                   title: string · status: "active"|"completed"
  TableScene       id: string · name: string
  CharacterRead    id,name,race,characterClass: string · level,currentHp,maxHp,armourClass: integer
                   abilities: {strength|dexterity|constitution|intelligence|wisdom|charisma: Ability}
                   appearance: string ("" possible) · backstory: string ("" possible) · items: Item[]
  Ability          score: integer · modifier: integer (signed, may be 0 or negative)
  Item             id: string · name: string
  ```
  `adventure`/`scene`/`campaignTitle` are null when no adventure was entered, the caller has no hero, or the
  pinned content no longer loads. `heroes` is every member character, ordered by member id, empty before
  character creation; `items` is one entry per unit — the client groups by name. `isAlive`/`down` stay
  off (← D7).
- I2 — `service.get_table(db, *, user_id: str, run_id: str) -> TableRead`
- I3 — `service.character_read(obj: GameObject, *, items: Sequence[GameObject] = ()) -> CharacterRead`
- I4 — `dice.ability_modifier(score: int) -> int`

Two design points the research fixed. The lobby's `get_run_overview` must not simply be extended: it drags
the whole adventure list through every refresh after a turn and carries no position. And the current
adventure is anchored on the acting hero's own adventure, not on whichever row reads as active — taking an
exit marks a row completed without clearing anyone's position, so the active-row anchor would blank the
header at exactly the adventure ending sprint 13 still has to show.

## Acceptance tests (qa)
No qa work item. AC1, AC2 → WI2 over the wire; AC3, AC4 → WI2, the hit-point one against the scratch
database, mirroring `tests/playthrough/test_acceptance_run_reads_for_screens.py`.

## Order
WI1, then WI2.
