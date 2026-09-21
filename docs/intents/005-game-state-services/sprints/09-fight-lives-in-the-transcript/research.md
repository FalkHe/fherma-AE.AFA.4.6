---
author: fhit:architect
owner: agent
created: 2026-09-21
---
# Research: sprint 09 — a fight happens entirely in the transcript

## Facts

- **Stats.** All four exist iff `kind='creature'` (`models.py:129-133`); `hp_range` already forbids `<0` and
  `>max_hp` (`:136-139`), so 0 is the column's own floor. A character takes them from the seed sheet
  (`service.py:305-312`), a monster from its template stat block (`:99-104`). A character is the row with `member_id`
  set and `template_id` NULL (`:303-313`); everything else has `member_id` NULL. `dice.py:113` tells a character by
  `template_id` instead — both hold today, but AC2 says *member-less*, so `damage` reads `member_id`.
- **`state`.** Plain JSONB, no `MutableDict` (`models.py:176`): an in-place key set is not tracked, the column must be
  reassigned whole. Written exactly once today, whole, from `CharacterState` (`schemas.py:78-89`, `service.py:313`):
  `abilities, race, character_class, background, appearance`. Monsters and items keep `{}`.
- **Attack roll.** `derive_formula`: `attack` → `1d20{to_hit:+}`, `damage` → the same `Attack.damage` string, off
  `context["item_id"]`'s template or the actor's own stat block, chosen by `context["attack"]`
  (`dice.py:126-153, 172-180`). A `roll` stores each die (`service.py:619-627`) and an attack is always one d20 —
  **natural 20 is `payload["faces"] == [20]`**, legible with no re-roll.
- **Consumption / refusal.** `_consume_roll` (`service.py:826-852`) requires same run, `kind` and `turn_id`, and no
  `ok` tool_call naming it in `rollIds` (`:779-795`); unknown or foreign → `NOT_FOUND`, else `RollNotUsableError`.
  `_refuse_*` appends `tool_call` `result: refused` at `dm` and commits it alone before the caller raises
  (`:853-886, 1384-1414`) — `append_event` only flushes (`:1731-1733`).
- **One action.** `_already_acted` counts `ok` tool_calls of this `turn_id` whose `name ∈ {interact, take, give,
  use_item, attack}` and whose `args["actorId"]` is the actor (`service.py:796-825`) — `attack` is already in the set,
  so `damage` needs no `actorId` and is free.
- **Gate order**, every acting mechanic: `_resolve_actor_and_run` → `_already_acted` (+refusal) → `_load_run_object`
  per id, foreign = unknown (`:1372-1382`) → own checks → write → `tool_call` `ok` → one commit (`:1416-1479`).
- **Goblin** (`campaign.json:47-68`): AC 13, 7 hp, *Rusty Shortsword* `+4`/`1d6+2` and *Sling* `+4`/`1d4+2` — two, so
  `context["attack"]` must name one (`dice.py:132-140`). Placed 3× in `lair-maw`, 1× in `lair-hollow`; the character
  starts in `village-green`, two exits away, carrying `shepherds-knife` (`+4`/`1d4+2`), AC 15, 12 hp.
- **No pending request.** `roll()` writes `roll_requested` *and* `roll` in one call (`service.py:670-698`), and
  `get_awaiting` only reports a request no `roll` answers by `requestId` (`:1793-1804`); `dm` rows never reach
  `list_events` (`:1748-1752`). AC3 = `get_awaiting == "none"` plus no player-visible `roll_requested`. Nothing in
  schema or code names an encounter or `in_combat`; `initiative` is only a `RollKind` (`schemas.py:125`).

## Work items

- **WI1 `attack`** — the mechanic and its three refusals; AC1, AC3's first half. No new error code.
- **WI2 `damage`** — hit binding, hp clamp, `is_alive`/`down`, `CharacterState.down`, one new domain code; AC2. Sole
  owner of `errors.py` / `core/errors.py`.
- **WI3 `roll_initiative`** — two rolls, no row written; AC4's first half.
- **WI4 acceptance suite** — AC1–AC4 black-box against the contracts below, plus the schema-wide assertion.
- **WI5 docs** — module `README.md` and `docs/modules/playthrough.md`, last of all.

WI1–WI4 are genuinely parallel once the interfaces are fixed: WI2 never calls `attack`, it only reads the event
`attack` recorded. The suite is red until WI1–WI3 merge.

## Interfaces

All `async`, `db` first, rest keyword-only with `user_id`, ending `turn_id: str | None = None`.

- `attack(db, *, user_id, actor_id, target_id, item_id: str | None = None, roll_id) -> str` returning
  `"hit" | "miss" | "crit"`. `item_id` is optional: a monster's attack comes from its stat block, not an item. Order:
  gate → `_already_acted` → load target and item → same-scene check (`give`'s shape, `service.py:1574-1579`) → item
  carried (`item.owner_object_id == actor.id`) → `_consume_roll(kind="attack")` → `crit` iff `faces == [20]`, else
  `hit` iff `total >= target.armour_class`, else `miss`. Writes no row. `tool_call` `ok`: `name "attack"`,
  `args {actorId, targetId, itemId?, rollId}`, `roll_ids [roll_id]`,
  `outcome {outcome, total, natural, armourClass}`. Refusals, each recorded then raised: already acted →
  `ALREADY_ACTED`; target in another scene or item not carried → `OBJECT_NOT_REACHABLE`; non-`attack`, spent or
  other-turn roll → `ROLL_NOT_USABLE`. Unknown or foreign ids → `NOT_FOUND`, unrecorded (← D12).
- `damage(db, *, user_id, target_id, roll_id, hit_id) -> int` returning the hp applied. `hit_id` is a `tool_call`
  **event id**: load it and refuse unless same run (else `NOT_FOUND`), `name == "attack"`, `result == "ok"`,
  `outcome["outcome"] in {"hit","crit"}` (a miss fails here), `event.turn_id == turn_id` (another turn fails here),
  `args["targetId"] == target_id`, and no `ok` tool_call of this turn with `name == "damage"` and
  `args["hitId"] == hit_id` (already damaged — `_roll_already_spent`'s scan, one key over). All five raise new
  `HitNotUsableError` / `HIT_NOT_USABLE` (409). The **target is read from that event's `args["targetId"]`**, never
  from the argument. Then `_consume_roll(kind="damage")`, `applied = min(total, current_hp)`; at 0,
  `member_id is None` → `is_alive = False`, else
  `state = CharacterState.model_validate(row.state).model_copy(update={"down": True}).model_dump()` — reassigned
  whole, `down: bool = False` added to `CharacterState`. `tool_call` `ok`: `args {targetId, rollId, hitId}`,
  `roll_ids [roll_id]`, `outcome {rolled, applied, currentHp, isAlive, down}`.
- `roll_initiative(db, *, user_id, side_a_ids, side_b_ids) -> tuple[Event, Event]`: per side, the first id whose row
  has a `member_id` goes through `request_player_roll(kind="initiative", context={})`, else
  `roll(..., visibility="player")`. No row write, no `tool_call`.

**AC4's negative claim.** One `database` test that plays a whole fight first, then asserts three *exact sets*, not
substrings: public `information_schema.tables`; `information_schema.columns` for `objects` and `events`;
`SELECT DISTINCT jsonb_object_keys(state) FROM objects`, which must equal `CharacterState`'s fields plus `down`. A
blacklist scan (`encounter`, `in_combat`, `turn_order`) reads well but is decorative alone — it would pass a table
named `fight_tracker`; the exact sets are what bites.

**Split?** No. 08b shipped four mechanics, four refusal paths and its suite as one sprint; this is three, one of them
a thin composition of existing calls, and AC4 is test-only. A split would also cut AC2 and AC3 from the `attack` event
they bind to.

## Open questions

- *Product-visible.* SRD rules win: a character at 0 hp is **dying** (unconscious, death saving throws), not dead —
  this sprint sets `down` and stops. Whether death saves are narrated, and what becomes of a run whose character never
  gets up, needs the product owner before phase 8.
- *Agent-level, calls made.* One new code for all five hit refusals (`ROLL_NOT_USABLE`'s precedent).
  `roll_initiative` writes no `tool_call`, against `decisions/mechanics.md`'s "every row appends at least one" — AC4
  allows only the two rolls, and a `tool_call` naming them would make them look spent. Both initiative rolls are
  `player`-visible (D7: narrated). An empty side list is a caller bug, not a domain refusal (← D1).
