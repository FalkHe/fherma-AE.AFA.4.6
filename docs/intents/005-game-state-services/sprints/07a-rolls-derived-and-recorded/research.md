---
author: fhit:architect
owner: agent
created: 2026-09-21
---
# Research: sprint 07 — a roll is derived, recorded and spent once

**Verdict first: split it.** Even compressed, this research sits over the cap — six graded surfaces, ~10 new
functions, a new file, a wire-shape change and a CLI command. Each half gets its own research.

## Facts

- **Payloads already shipped**, `playthrough/schemas.py`, `extra="forbid"`, stored `by_alias=True`:
  `RollRequestedPayload{kind, actor_id, formula, context: Any}` (`:141`) ·
  `RollPayload{request_id?=None, kind, actor_id, formula, faces[int], modifier, total}` (`:156`; the last three
  **required**, so a no-die event cannot be a `roll`) · `QuestionPayload{text, options[str]}` (`:169`; `options`
  has **no default**) · `ToolCallPayload{name, args, roll_ids[], result: ok|refused, outcome}` (`:177`) ·
  `RollKind = attack|damage|ability_check|saving_throw|initiative|custom` (`:114`). All four types are in
  `EVENT_PAYLOADS` (`:209`), which `append_event` validates against — `add`+`flush`, **no commit**, no membership
  check (`service.py:646`).
- **Formulas in content**: `Attack{name, to_hit: int, damage: ProseText}` (`content/schemas.py:23`) — `to_hit` the
  *complete* d20 bonus, `damage` a verbatim expression (`"1d6+2"`), unvalidated by the loader
  (`docs/modules/content.md:112`); on `ItemTemplate.attacks` (`:52`) **and** `CreatureTemplate.stat_block.attacks`
  (`:33`) — greenhollow's goblin has two natural attacks and no item, `wooden-shield` none; read via
  `load_object_template` (`content/service.py:364`).
- **Abilities live in two places**: a template-born creature keeps `state = {}`, its six scores (1–30,
  `content/schemas.py:14`) in `stat_block.abilities` via `template_id` (`service.py:69`); a character has
  `template_id = NULL` and snake_case scores in `objects.state["abilities"]` (`:293`). No modifier helper exists;
  `(score - 10) // 2` is new.
- **`events`** (`models.py:183`-`221`): `turn_id` nullable `CHAR(26)`, **no referent, no allocator** — every event
  so far stores `NULL`, `use_exit` takes none · `visibility ∈ player|dm` (`:216`) · `actor_member_id` nullable FK
  (`:211`) · `ix_events_campaign_run_id_turn_id` (`:204`) covers `(campaign_run_id, turn_id)`, exactly the
  consumption scan.
- **Recorded refusal, the pattern to copy** (`service.py:512`-`537`): `_refuse_exit` appends `tool_call`
  `result:"refused"` at `dm` with a `reason` in `outcome` and **commits it alone** before the caller raises —
  `append_event` only flushes, so without that commit a rollback erases the record. Gate order: the object by id
  alone (`:499`) → `_require_member` (`:134`) → `_get_run` → `_require_writable` (`:225`) → `ready|active`.
- **CLI precedent**: `app playthrough cost` (`commands.py:28`-`49`) opens its own session via
  `get_sessionmaker()`, prints plain lines, writes `f"{exc.code}: {exc}"` to stderr with exit 1; its test
  monkeypatches the service *module attribute*, no database. RNG seam `core/llm/retry.py:44`.

## Work items, and the split

WI1 `dice.py` · WI2 `derive_formula`, and reading an actor's abilities and attacks · WI3 the four producers and
`ask_player` · WI4 `_consume_roll`, `resolve_check`, `resolve_save`, the refusals and their codes · WI5
`get_awaiting` and the events response · WI6 `app playthrough roll` · WI7 acceptance tests · WI8 docs.
**WI1 → WI2 → WI3 → WI4 is sequential** (one `service.py`; each needs the previous one's output to test against);
WI5 and WI6 need WI3. Only WI1 and WI8 are parallel, so splitting costs no parallelism.

- **07a — a roll is derived and recorded** (AC1, AC2, `ask_player`): WI1, WI2, WI3, WI6. Verified by
  `app playthrough roll` printing a derivation no caller supplied, plus `database` tests over the
  `roll_requested`→`roll` pair and the hidden passive check.
- **07b — a roll is spent once, and the client sees what is awaited** (AC3, `get_awaiting`): WI4, WI5. Verified by
  `database` tests on pass/fail and the four refusals, plus `awaiting` on `GET …/events`.

**07b depends on 07a**: nothing to consume, nothing to await, until the producers exist.

## Interfaces — the contracts that cross the line

Every function: `async`, `db` first, rest keyword-only, plus `turn_id: str | None = None` — phase 8 passes a real
one; today everything lands in the untagged turn.

- `dice.roll(expression) -> DiceRoll{faces, modifier, total}`, `NdM±K`, behind `dice._rng() -> random.Random`;
  anything else raises `InvalidDiceExpressionError` naming the expression (→ `VALIDATION_ERROR`).
- `derive_formula(kind, actor, context, *, campaign_id, version) -> str` — AC1's mapping kind by kind; the attack
  comes from `context.item_id`'s template when given, else the actor's own stat block.
- Producers, each resolving the run from the id it is given, then `use_exit`'s gate order:
  `request_player_roll(user_id, actor_id, kind, context) -> Event`, its id the request id ·
  `resolve_roll_request(user_id, request_id) -> Event`, re-using the request's stored `formula`, `kind`, `actor_id`
  and `visibility` · `roll(user_id, actor_id, kind, context, visibility="dm") -> Event` ·
  `passive_check(user_id, actor_id, ability, dc) -> bool` · `ask_player(user_id, run_id, text, options)`.
- Consumers: `resolve_check(user_id, roll_id, dc) -> bool` and `resolve_save(…)`, appending
  `tool_call{name, args{rollId, dc}, rollIds:[roll_id], result:"ok", outcome{total, dc, success}}` at `dm` (← D11:
  pass/fail lives here, not on the roll) · `get_awaiting(user_id, run_id) -> "none"|"roll:<id>"|"answer:<id>"` from
  the open turn's events, attached as `EventsRead{events:[…], awaiting}`.
- New `ErrorCode`s (`core/errors.py:17`, `:50`): `ROLL_NOT_USABLE`, `INVALID_DC`, both 409; an unknown roll id
  stays `NOT_FOUND`. CLI: `app playthrough roll <kind> --actor --user [--ability|--item|--attack|--expression]`
  prints kind, actor, formula, faces, modifier, total; errors as `cost`.

**"Never a number a caller passed" (← D6) is structural**: no producer takes `formula`, `modifier`, `bonus`,
`faces` or `total` — there is no parameter to pass one through. The only caller numbers are `dc` (range-checked)
and `expression`, reachable only under `kind="custom"`, never mixed with a derived bonus, and refused by both
consumers and by 09's combat.

**`_consume_roll(run_id, roll_id, kind, turn_id)` decides from events alone**, no column: the event exists, is
`type="roll"`, belongs to `run_id` · `payload["kind"] == kind`, so `custom` fails every check · its `turn_id`
equals the consuming call's, `IS NULL` when both are untagged · no `tool_call` in that same
`(campaign_run_id, turn_id)` with `result == "ok"` already names `roll_id` in `rollIds` — a *refused* attempt must
not burn the roll. Each failure is recorded and committed as above, then raised.

**The events response changes shape**, no longer the bare array of `routes.py:142`-`159`. Nothing outside the
backend reads it — no playthrough code in the frontend, no playthrough path in `schema.d.ts` — so the blast radius
is two tests asserting a list (`test_routes.py:812`, `test_acceptance_transcript_writer_and_read.py:346`) plus the
regenerated schema.

## Open questions

- **Product-visible**: content authors DCs from 1 (`content/schemas.py:57`,`:75`) but AC3 refuses a `dc` below 5,
  so an authored DC of 3 is unresolvable. Call: 5–30 binds the two consumers only — confirm, or narrow content.
- **Product-visible**: a monster's attack is not an item, so `attack` derivation falls back to the actor's stat
  block and needs a name when several exist. Confirm that choice is the DM's.
- *Agent-level calls*: `passive_check` records a `tool_call` at `dm`, not a `roll` (which needs `faces` and would
  be consumable) · `_acted_this_turn` belongs to 08 · `dice` caps an expression at 20 dice of ≤100 faces.
