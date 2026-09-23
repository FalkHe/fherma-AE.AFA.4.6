---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 04

Research sliced this six ways; three of those are a few lines each, so they are grouped by the file they
own. No work item touches another's files.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The four new player-visible entry kinds exist and are validated: the database accepts them, their payloads are typed, and the module's list of kinds is documented | each new kind's payload validates and a malformed one is refused before any row is written; the widened constraint reverses cleanly | – |
| 2 | backend-python | Every world-changing mechanic leaves a visible entry carrying who, what and the numbers before and after; refusals and private mechanics leave none | taking, dropping and giving each leave one entry naming hero and item; damage leaves one with the hit points before and after; opening a way leaves one only when it succeeded; entering a scene carries the scene's title; a refused action and a private check leave nothing | interfaces I1, I2 |
| 3 | backend-python | Looking up a rule leaves a visible entry naming the topic and never the rules text | a matched lookup leaves one entry with the heading; a lookup that matched nothing leaves none; the model's own words never reach the entry; a turn that looks up a rule and takes an item leaves exactly two visible entries and no others | interfaces I1, I3 |

## Interfaces
New event types, all `visibility="player"`, payload keys exactly as stored and served (camelCase):
- I1 — payload shapes:
  - `item_moved` — `movement: "taken"|"dropped"|"given"`, `actorId: str`, `actorName: str`, `itemId: str`,
    `itemName: str`, `toId: str|None = None`, `toName: str|None = None` (`given` only).
  - `hp_changed` — `targetId: str`, `targetName: str`, `before: int`, `after: int`, `maxHp: int`,
    `alive: bool`, `down: bool`.
  - `way_opened` — `actorId: str`, `actorName: str`, `objectId: str`, `objectName: str`, `action: str`
    (the authored action verbatim, e.g. `"pick_lock"`).
  - `rule_looked_up` — `topic: str` (the best match's full `heading_path`, e.g.
    `"Chapter 7 › Using Ability Scores › Hiding"`). Never the rules text, never the model's query.
  - `scene_entered` — existing `adventureRunId: str`, `sceneId: str`, plus `sceneTitle: str|None = None`
    (read from pinned content; absent on older rows).
  `ck_events_type` widens to sixteen values, self-reversing, mirroring migration 0007 plus its test.
- I2 — where the writes go: `take`/`drop`/`give` append `item_moved`; `damage` appends `hp_changed`;
  `interact` appends `way_opened` **on success only** (a failed check changed nothing); `use_exit` and
  `enter_adventure` append `scene_entered` carrying the destination's title. Each inside the mechanic's
  existing transaction. Refusal and `dm`-visibility paths are untouched.
- I3 — `async def record_rule_lookup(db, *, user_id: str, run_id: str, topic: str, turn_id: str | None = None) -> Event`
  in `playthrough/service.py` — `_require_member`, append, commit; the module's ordinary mechanic shape.
  Owned by WI2 (it owns that file); called by WI3 from the `lookup_rule` tool when the search matched and
  `ctx.run_id` is set. No row when nothing matched.

AC4 is structural, not a feature: `append_event` is the only event writer, no tool calls it, and every
string in the new payloads is read by the server from stored object names, pinned content or the rule
heading — never from a tool argument. WI1 owns a test that pins this.

## Acceptance tests (qa)
No qa work item — the backlog reserves acceptance tests for sprint 03. AC1 → WI3, AC2 → WI2, AC3 → WI2
and WI3, AC4 → WI1.

## Order
Parallel: WI1, WI2, WI3. WI2 and WI3 implement against I1 without waiting.
