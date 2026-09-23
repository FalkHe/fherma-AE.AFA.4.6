---
author: fhit:architect
owner: agent
created: 2026-09-23
---
# Research: sprint 010-04

## Facts

**The twenty tools** (`game/agent/tools.py:713-734`, names in `agent/state.py:14-33`). World-changing: `take` (`playthrough/service.py:1769`), `drop` (:1834), `give` (:1885), `damage` (:2294), `interact` (:1520), `use_exit` (:1375). Private (write `tool_call` at `dm`): `resolve_check` (:1314), `resolve_save` (:1331), `passive_check` (:1052), `attack` (:2058 — changes no row by design, :2061-2064). Write nothing at all: `lookup_rule`, `recall`, `get_scene`/`get_object`/`get_campaign`. Refusable, each recording a `dm`-only `tool_call result:"refused"` before raising: `interact`/`take`/`give`/`use_item`/`attack`/`damage`/`use_exit` (`_refuse_*`, :1223,1359,1503,1752,2041,2281). `use_item` refuses unconditionally (:2002-2016) — **nothing in the backend can raise hit points**; `grep heal` finds no mechanic, so `damage` is the only writer of an hp line today.

**Events.** `append_event` (:2407) is the only constructor of `Event` rows, proven tree-wide by an AST test (`tests/playthrough/test_only_event_writer.py:1-15`). It validates `payload` against `EVENT_PAYLOADS[type]` (`playthrough/schemas.py:325-338`, twelve types, each model `extra="forbid"`), stores it `by_alias=True` (camelCase in storage, :2491), flushes without committing, and rejects an unknown `type`. The same twelve names are a DB CHECK (`models.py:207-212`); widening it is an additive migration with precedent (`alembic/versions/0007_lifecycle_and_event_types.py:34-63`, tested in `tests/playthrough/test_migration_0007.py`).

**The player-facing read.** `list_events` (:2521) filters `visibility == "player"` in SQL (:2542); `EventRead` (`schemas.py:102-113`) carries `id, type, turnId, payload, createdAt` with `payload: dict[str, Any]` passed through unmapped. So a new kind needs migration + payload model + registry entry and **no route, schema.d.ts or read change**; older transcripts simply hold no such rows (no backfill, no re-validation on read) and sprint 06 must ignore types it does not know. Already `player`-visible: `narration`, `player_action`, `question`, `roll_requested`, `roll`, `scene_entered`, `adventure_started`, `adventure_completed`.

**Numbers each mechanic already holds when it runs.** `take`/`drop`/`give` load actor and item rows (`_load_run_object`, :1725) → `name` of both, and `give` also the receiver's. `damage` (:2369-2380) holds `before = target.current_hp`, `applied`, `after`, `max_hp`, `is_alive`, `down`. `interact` (:1670-1678) holds actor, fixture row, the authored `action` and `success`; its `dc` and roll total stay `dm`-only today. `use_exit` (:1440-1450) writes `scene_entered {adventureRunId, sceneId}` at `player` but no scene title and no actor; `enter_adventure` (:774) positions everyone at the entry scene and writes **only** `adventure_started` — the opening scene leaves no `scene_entered` at all.

**AC4 is structural.** The model can choose *which* mechanic runs; it cannot author a line. (1) only `append_event` writes; (2) no tool calls it — tools are thin calls into `playthrough.service` (`tools.py:1-7`), and the sole event writes outside that module are `player_action`/`narration` in `agent/nodes.py:241,350`; (3) of the new payloads below, every string is read by the server from `objects.name`, pinned content or `srd_rules.heading_path`, and every number from `objects.current_hp/max_hp` — no tool argument is passed through as prose. `interact.action` is model-supplied but must match an authored `FixtureCheck.action` by exact equality before the ok path (:1614-1628), so it is authored content. Pre-existing, unchanged: `ask_player.text/options` land in a `player` `question` (← D2) and `roll_dice.context` lands free-form in a `player` `roll_requested` (`schemas.py:257-269`).

**Bug on the rule path.** `tools.py:704` does `" > ".join(m.heading_path)`, but `RuleMatch.heading_path` is already one string joined with `" › "` (`srd/schemas.py:36`, built at `srd/service.py:178`) — the join currently splays it character by character.

## Work items

- WI1 migration: widen `ck_events_type` to sixteen values (`item_moved`, `hp_changed`, `way_opened`, `rule_looked_up`), self-reversing, mirroring 0007 plus its migration test.
- WI2 payloads: the four `EventPayload` models and their `EVENT_PAYLOADS` entries, plus `sceneTitle` on `SceneEnteredPayload`; unit tests over `append_event` validation.
- WI3 mechanic writes (`playthrough/service.py`): `take`/`drop`/`give` append `item_moved`, `damage` appends `hp_changed`, `interact` appends `way_opened` **on success only** (a failed check changes nothing — D12 §40 "a small line for anything that changed"), `use_exit` and `enter_adventure` append `scene_entered` carrying the destination's title. Each inside the mechanic's existing transaction, `visibility="player"`; refusal and `dm` paths untouched.
- WI4 rule line: new `playthrough.service.record_rule_lookup`, called by the `lookup_rule` tool when the search matched and `ctx.run_id` is set; fix the `heading_path` join.
- WI5 acceptance test: one turn that looks up a rule and takes an item leaves exactly two new `player` rows and no others; a refused `take` and a `passive_check` leave none.
- WI6 docs: `playthrough/README.md` event-kind list and surface note.

WI1 ∥ WI2; then WI3 ∥ WI4 ∥ WI6; WI5 last.

## Interfaces

New event types, `visibility="player"`, payload keys exactly as stored and served (camelCase):

- `item_moved` — `movement: "taken"|"dropped"|"given"`, `actorId: str`, `actorName: str`, `itemId: str`, `itemName: str`, `toId: str|None = None`, `toName: str|None = None` (`given` only).
- `hp_changed` — `targetId: str`, `targetName: str`, `before: int`, `after: int`, `maxHp: int`, `alive: bool`, `down: bool`. Covers healing unchanged when a consumable exists.
- `way_opened` — `actorId: str`, `actorName: str`, `objectId: str`, `objectName: str`, `action: str` (the authored action verbatim, e.g. `"pick_lock"`).
- `rule_looked_up` — `topic: str` (the best match's full `heading_path`, e.g. `"Chapter 7 › Using Ability Scores › Hiding"`; sprint 06 renders its last segment). Never the rules text, never the model's query; no row when nothing matched.
- `scene_entered` — existing `adventureRunId: str`, `sceneId: str`, plus `sceneTitle: str|None = None` (read from pinned content; absent on older rows).

`async def record_rule_lookup(db, *, user_id: str, run_id: str, topic: str, turn_id: str | None = None) -> Event` — `_require_member`, append, commit; the module's ordinary mechanic shape.

Trade-off: four narrow types rather than one `system` line with a message, because `NoticePayload.message` is wording and the game produces none; failure behavior is `InvalidEventPayloadError` before any row is written; blast radius is `playthrough/schemas.py`, six call sites in `playthrough/service.py`, one tool and one migration — no route, no client regeneration.

## Open questions

None product-visible. Note for the backlog: nothing in the game can heal yet, so the hit-point line only ever falls today.
