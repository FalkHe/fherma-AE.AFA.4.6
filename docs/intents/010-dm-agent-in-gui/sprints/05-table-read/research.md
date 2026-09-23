---
author: fhit:architect
owner: agent
created: 2026-09-23
---
# Research: sprint 010-05 — the table read

## Facts

**The existing read.** `GET /playthrough/runs/{run_id}/overview` (`routes.py:71-82`) →
`service.get_run_overview` (`service.py:396-478`) → `CampaignRunOverviewRead` (`schemas.py:95-115`): run row,
campaign title/summary, `unavailable`, `members[]` (`CampaignRunMemberRead`, `schemas.py:68-79`) and
`adventures[]` — every campaign adventure with a clipped intro and done/active/unplayed. It carries **no
current adventure, no scene, no ability scores, no backstory, no items**. It is the lobby's read: content-wide,
stale-cached 30 s in `useRunOverview.ts:20-60`. The table read is refetched after every turn (AC3), so
extending it would drag the whole adventure list through each turn and give the lobby scene fields it cannot
use. Keep two routes, **share one hero shape** (below) — that is what "009's card reuses this read" costs.

**Hero fields.** `CharacterRead` (`schemas.py:49-66`) = `id,name,currentHp,maxHp,armourClass,race,
characterClass,level,appearance`, built by `service.character_read` (`service.py:375-394`) and used by both the
overview and `POST /campaign/{runId}/character`; the frontend card binds it directly
(`CharacterCard.tsx:21`). Columns on `objects`: `current_hp,max_hp,armour_class,is_alive`
(`models.py:179-182`). Everything else is stored in the `state` JSONB as `CharacterState`
(`schemas.py:170-203`): `abilities` (six ints, `content/schemas.py:16-22`), `race`, `character_class`,
`level` (default 1), `appearance`, and **`background`, which is written from the sheet's `backstory`**
(`service.py:531`; the seed hero's own `background`, `service.py:546`). Carried items are separate rows —
`owner_object_id = character.id`, one row per unit of quantity (`service.py:565-598`).

**Modifiers are computed, never stored** — `(score - 10) // 2`, floor division: `dice._ability_modifier`
(`dice.py:98-102`), re-exported by `character/builder.py:132-133` through a `noqa: SLF001` seam, and
duplicated a third time in `character/service.py:142-145` for prompt rendering.

**Adventure and scene.** `adventure_runs` holds `adventure_id` + `status` active/completed, at most one
`active` per run (`models.py:98-103`). Position lives on the hero: `enter_adventure` writes
`adventure_run_id` + `scene_id = adventure.entry_scene` onto every member character (`service.py:790-796`);
`use_exit` rewrites `scene_id` on a scene exit and, on `adventure_end`, sets the row to `completed`
**without clearing anyone's position** (`service.py:1476-1503`). So anchoring "current adventure" on
`status == 'active'` blanks the header the moment an adventure ends (sprint 13 still needs it). Anchor on the
**acting hero's own `adventure_run_id`** and return that row's `status`. Titles come from pinned content:
`_load_pinned(run)` → `loaded.adventures[id].title`, `loaded.scenes[id].title` (`content/schemas.py:108-125`,
`content/service.py:76`). The agent's own context builder already reads the scene this way, off the first
character with a `scene_id` (`game/agent/nodes.py:123-127,149-152`).

**The acting hero** is concretely the caller's member character — `kind='creature' AND member_id = member.id`,
`service.get_member_character` (`service.py:610-634`), which is exactly what `run_turn` acts with
(`game/service.py:219`).

**The gate.** `_require_member` (`service.py:173-189`) is the first call of every run-scoped function: unknown
run and foreign run both raise `CampaignRunNotFoundError` → `ErrorCode.NOT_FOUND` (`errors.py:23-31`) → 404
`{"error":{"code":"NOT_FOUND",…}}` (`core/errors.py:_ERROR_INFO`). That is AC4, unchanged.

**Conventions.** Route declares its response model as the return type plus `{401,404: ErrorEnvelope}`, calls
one service function, maps `PlaythroughError` → `ApiError`, no commit (`routes.py:63-82`). Wire models
subclass `CamelModel` (`core/schemas.py:7-8`). Typed client: `make generate-api` (`Makefile:86-88`, stack up)
rewrites the committed `frontend/src/api/schema.d.ts`; `frontend/src/api/schema.runReads.test.ts` is the
precedent for asserting a generated shape. Widening `CharacterRead` is additive — no frontend break.

## Work items

- **WI1 (backend):** one hero shape — widen `CharacterRead` with `abilities`, `backstory`, `items`; make
  `dice.ability_modifier` public (drop builder.py's `noqa` seam); `character_read` takes the carried rows;
  `get_run_overview` supplies them from one grouped query (no N+1). 009's card then gains the fields free.
- **WI2 (backend, after WI1 — same two files):** `TableRead` + `service.get_table` + the route.
- **WI3 (qa, parallel with WI1/WI2):** acceptance tests against I1-I4 — AC1/AC2 over the wire with a stubbed
  service, AC3 and AC4 `@pytest.mark.database` against the scratch db, mirroring
  `tests/playthrough/test_acceptance_run_reads_for_screens.py`.
- **WI4 (after WI1+WI2):** `make generate-api`, commit `schema.d.ts`, static shape test.

## Interfaces

**I1 `GET /api/v1/playthrough/runs/{run_id}/table` → 200 `TableRead`** · 401 · 404 `NOT_FOUND` (unknown or
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
pinned content no longer loads (`_load_pinned` → `None`). `heroes` is every member character, ordered by
member id, empty before character creation; `items` is one entry per unit — the client groups by name.
`isAlive`/`down` stay off (← D7).

**I2** `service.get_table(db, *, user_id: str, run_id: str) -> TableRead` · **I3**
`service.character_read(obj: GameObject, *, items: Sequence[GameObject] = ()) -> CharacterRead` · **I4**
`dice.ability_modifier(score: int) -> int`.

## Open questions

None product-visible. Assumptions for veto: the header's back link uses `runTitle ?? campaignTitle` (D12's
prose says run, its string table says campaign); identical items arrive as separate rows.
