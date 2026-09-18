---
author: sprint
owner: agent
created: 2026-09-18
---
# Plan: Sprint 04

Amended by the product owner: no unarchive, a finished game may be archived, a never-started one is deleted by it.
AC3's "flip `active|ready ↔ archived`" is superseded; the rest of the brief stands.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The game gets its character — one creature owned by the member, carrying the seed pack as real items — and becomes ready; renaming; archiving, which deletes a never-started game; an archived game refuses every write | AC1–AC4, per the criteria and I3–I5 | – |
| 2 | backend-python | Those endpoints, in the wire's vocabulary, the envelope for every refusal, rename reachable from a browser | AC1, AC3: the three responses, each refusal's code, a `PATCH` preflight | WI1, I1–I5 |
| 3 | backend-python | The general model doc splits starting a game from creating its character and states the new shelf life; README and playthrough doc list what exists | AC4 | I1–I5 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I5 |

## Interfaces
- I1 Routes, all under `/api/v1/playthrough`, all `CsrfAuth`:

  | Method | Path | Body | Response |
  |---|---|---|---|
  | POST | `/campaign/{run_id}/character` | — | 201 `CharacterRead` |
  | PATCH | `/campaign/{run_id}` | `{"title": str}` | 200 `CampaignRunRead` |
  | POST | `/campaign/{run_id}/archive` | — | 204, no body |

  `PATCH` joins `allow_methods` in `main.py` (today `GET, POST, OPTIONS`) or rename passes every test and fails in a browser.
- I2 `CharacterRead` (`CamelModel`): `id, name, currentHp, maxHp, armourClass`, nothing else. `RenameCampaignRunRequest`: `title: str = Field(min_length=1, max_length=120)`.
- I3 Service, `service.f(...)`, `_require_member` first in each:
  - `create_character(db, *, user_id, run_id, sheet: SeedCharacter | None = None) -> GameObject` — `None` reads the pinned seed; phase 7 passes a sheet, the signature unchanged (← D4)
  - `rename_campaign_run(db, *, user_id, run_id, title) -> CampaignRun`
  - `archive_campaign_run(db, *, user_id, run_id) -> None` — `ready|active|finished → archived`; a `setup` run is deleted outright, member and objects with it; already archived is a no-op. No unarchive exists
  - `activate_campaign_run(db, *, user_id, run_id) -> CampaignRun` — `ready → active`, already `active` a no-op, else `InvalidRunStatusError`. **No route** (← D3; phase 8 calls it)
  - `_require_writable(run)` — internal; `RunArchivedError` on `archived`; used by rename, character and sprint 06
- I4 `create_character` pre-checks for a creature with this `member_id` → `CharacterExistsError` (a game rule, not a constraint ← 003-D13); builds the creature, flushes, one carried row per pack entry through sprint 03's `_build_object` (widened: `source_*` optional), flushes, sets `ready`, commits once. No event. Keys `pc:<member_id>:1`, carried `pc:<member_id>:1/<template_id>:<n>`, `n` counting repeats in the pack.
- I5 `state` (`playthrough/schemas.py`, plain `BaseModel`, written whole): `CharacterState{abilities, race, character_class, background, appearance}`; carried items keep `{}`. Errors, each a new `ErrorCode`, all 409: `RunArchivedError → RUN_ARCHIVED`, `CharacterExistsError → CHARACTER_EXISTS`, `InvalidRunStatusError → INVALID_RUN_STATUS`. Sprint 03's wide `except IntegrityError` is **not** copied: `create_character` catches nothing.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_character_and_shelf_life.py`; AC2 `@pytest.mark.database`.
- AC1 → the first character answers 201 and leaves the game ready; a second is refused.
- AC2 → the character's row and carried pack: keys, hit points, no template, no position.
- AC3 → rename; archive from ready, active, finished; a never-started game disappears; an archived one reads, refuses writes.
- AC4 → `activate_campaign_run` moves ready to active, with no route.

## Order
Parallel: WI1, WI3, qa. Then: WI2.
