---
author: fhit:architect
owner: agent
created: 2026-09-18
---
# Research: sprint 04

## Facts

**The sheet.** `SeedCharacter` (`content/schemas.py:126`-`135`): `name, race, character_class, background,
appearance` (`ProseText`, **no max length**), `abilities` (six ints), `max_hp`, `armour_class`, `inventory:
list[ContentId]` — sprint 01's R20 (`content/service.py:317`) already guarantees each entry names an existing
**item** template. `greenhollow/v1`: ac 15, hp 12, five distinct ids. Read off the run's own pin, never re-pinned:
`load_campaign(run.campaign_id, run.content_version).campaign.seed_character` (← 003-D7; `service.py:131` is the
only version resolution).

**The generic object write.** `_build_object` (`service.py:24`-`55`) generates the id, copies
`kind/template_id/name` off an `ObjectTemplate`, fills the four stats from `stat_block`, and takes
`source_adventure_id`/`source_scene_id` as **required** kwargs. Reusable for the carried items once those two become
`str | None = None`; **not** for the character — no template, stats from the sheet — so that row is built inline.
Flush order (`service.py:138`-`156`): owner added and flushed, then the carried rows; no ORM relationship orders
them and `owner_object_id` is a real FK.

**`instance_key`.** Sprint 03's reading of ASSUMPTION 9 (`service.py:80`,`:93`):
`<adventure>:<scene>:<template>:<ordinal>`, carried `<owner_key>/<template>:<ordinal>`. `pc:<member_id>:1` puts the
literal `pc` where the provenance triple was — 31 chars, carried ~50, inside `String(160)` (`models.py:161`);
uniqueness is `uq_objects_campaign_run_id` (`:126`).

**Columns.** The character sets `member_id` and the four stats; NULL are `template_id`, `source_adventure_id`,
`source_scene_id`, `adventure_run_id`, `scene_id`, `owner_object_id`. `stats_creature_only` (`models.py:128`) wants
all four stats on a creature and all four **absent** on each carried item; `hp_range` (`:135`) wants
`0 ≤ current_hp ≤ max_hp`, so both are `sheet.max_hp`; `ck_objects_carried` (`:142`) bars a position on anything
owned. `state` is `Mapped[dict]` over JSONB, `server_default '{}'`, **no per-kind validation anywhere**
(`:176`, ← intent §C1); NPCs keep `{}` because `template_id` reaches their abilities, the character has no template,
so `state` is the only place its abilities and prose can live. Reassign whole, never mutate.

**Gate, errors, wire.** `_require_member` (`service.py:107`) opens every run-scoped function; unknown and foreign
alike raise `CampaignRunNotFoundError` (← D12). Routes translate one way (`routes.py:30`) into the shared
`ErrorCode` enum and its status/message table (`core/errors.py:17`,`:44`). `CamelModel` (`core/schemas.py:7`) both
directions; `CurrentAuth`/`CsrfAuth` (`auth/dependencies.py:37`,`:47`) are method-agnostic.
`allow_methods=["GET","POST","OPTIONS"]` (`main.py:28`) — **`PATCH` fails a browser preflight** where `TestClient`
would not (`tests/core/test_cors.py:17`). `schema.d.ts` stays ungenerated, as after 03.

## Work items

WI1–WI5 are parallel against the interfaces below; only WI6 is sequential, describing what landed. WI3/WI4 stay
red until WI1/WI2 land — not a dependency.

- **WI1 service + errors** (`service.py`, `errors.py`, `core/errors.py`): the character write, its inventory, the
  four transitions, the archived-write refusal, the codes. AC1–AC4.
- **WI2 routes + schemas** (`routes.py`, `schemas.py`): the four endpoints and the `state` model. AC1, AC3.
- **WI3 route tests** (`tests/playthrough/test_routes.py`, stubbed session, service monkeypatched): status codes,
  camelCase field sets, auth/CSRF, each new code's envelope. AC1, AC3.
- **WI4 database acceptance** (`tests/playthrough/test_acceptance_character_and_shelf_life.py`,
  `@pytest.mark.database`): AC2's row claims, the status flips, archived read-vs-write, plus AC4's
  `activate_campaign_run` unit test. AC2–AC4.
- **WI5 CORS** (`app/main.py`, `tests/core/test_cors.py`): add `PATCH` and a preflight test — without it rename
  passes in tests, fails in a browser. AC3.
- **WI6 documentation**: `model.md`'s lifecycle rows have shifted to `:314`-`:315` — split the start row in two and
  add rename/unarchive; `playthrough/README.md:72` §Surface and `docs/modules/playthrough.md:237` §8 still say
  "three endpoints" and need seven plus the new functions (§3 `:62` already lists the five statuses). AC4.

## Interfaces

Under `/api/v1/playthrough`, all `CsrfAuth`, all answering `CampaignRunRead` (`schemas.py:65`) but the character.

- `PATCH /campaign/{run_id}`, body `{"title": …}` → 200
- `POST /campaign/{run_id}/character` → 201 `CharacterRead`
- `POST /campaign/{run_id}/archive` → 200 · `POST /campaign/{run_id}/unarchive` → 200

`CharacterRead(CamelModel)`: `id, name, currentHp, maxHp, armourClass`, nothing else (AC1).
`RenameCampaignRunRequest`: `title: str = Field(min_length=1, max_length=120)`.

**Service** (`service.f(...)`, `_require_member` first):

- `create_character(db, *, user_id, run_id, sheet: SeedCharacter | None = None) -> GameObject` — `None` reads the
  pinned seed; phase 7 passes a sheet and the signature does not change (← D4).
- `rename_campaign_run(db, *, user_id, run_id, title) -> CampaignRun`
- `archive_campaign_run(db, *, user_id, run_id) -> CampaignRun` — `ready|active → archived`; already archived a
  no-op; `setup|finished` raise `InvalidRunStatusError`.
- `unarchive_campaign_run(...)` — `→ active` if a `narration` event exists, else `→ ready`; non-archived a no-op.
- `activate_campaign_run(...)` — `ready → active`, already `active` a no-op, else `InvalidRunStatusError`. **No
  route** (← D3; phase 8 calls it).
- `_require_writable(run)` — internal; `RunArchivedError` on `archived`. Used by rename, character, and sprint
  06's `enter_adventure`.

`create_character` pre-checks for a creature with this `member_id` → `CharacterExistsError` (a game rule, not the
constraint — ← 003-D13), builds the creature, flushes, builds one carried row per inventory entry through the
widened `_build_object`, flushes, sets `status = "ready"`, commits once. Appends no event.

**Keys.** `pc:<member_id>:1`; carried `pc:<member_id>:1/<template_id>:<n>`, `n` counting repeats of that template
id within the inventory list (greenhollow's five are distinct → all `:1`).

**`state`** (`playthrough/schemas.py`, plain `BaseModel`, written whole via `model_dump()`):
`CharacterState{abilities: content.schemas.Abilities, race, character_class, background, appearance}`. Carried
items keep the `{}` default.

**Errors** (`errors.py`, each a new `ErrorCode` + `_ERROR_INFO` row, all 409): `RunArchivedError → RUN_ARCHIVED`,
`CharacterExistsError → CHARACTER_EXISTS`, `InvalidRunStatusError → INVALID_RUN_STATUS`.

**On sprint 03's precedent.** Its `content.schemas`/`content.errors` imports stand — the schemas are content's
published return type, and re-raising `ContentNotFoundError` as `CampaignNotFoundError` enforces a boundary. Its
wide `except IntegrityError:` (`service.py:157`) must **not** be copied: the same block here can violate
`stats_creature_only`, `hp_range` and two FKs, and a tidy 409 over any of those hides a bug. `create_character`
catches nothing — its one rule is the pre-check, every other failure travels to the 500 envelope. Narrowing 03's
catch to the `uq_objects_campaign_run_id` name is a `Backlog proposals` line.

## Open questions

- **Product-visible.** What does unarchiving restore? `archived` overwrites the only status column. **Called:**
  derive it — a run with a `narration` event was `active`, one without `ready`. The cheaper "always `ready`" is
  self-healing but labels a played run "ready to play" for one turn. No narration exists yet, so the test forces
  the case with a raw event row.
- **Product-visible.** AC3 archives only `ready|active`, so an abandoned `setup` run and a `finished` one cannot
  be put away. Following the brief, flagging the gap.
- **Agent-level, called.** `PATCH` over `POST …/rename`; title required and non-empty, clearing it to `NULL` is not
  offered. `ProseText` has no max length while `objects.name` is `String(120)`: no truncation, no guard — phase 7
  feeds generated text there and must revisit it.
