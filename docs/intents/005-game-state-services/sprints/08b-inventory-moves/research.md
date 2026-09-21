---
author: fhit:architect
owner: agent
created: 2026-09-21
---
# Research: sprint 08 — the world's objects answer to the mechanics

**Verdict: split it**, at 06's mechanic boundary — 08a `interact` + the one-action rule (AC1, AC3), 08b the
inventory moves + the `use_item` seam (AC2, AC4).

## Facts

- **Row → template → checks.** `objects.template_id` (`models.py:160`, nullable) →
  `content.service.load_object_template(run.campaign_id, run.content_version, id)` (`content/service.py:364`) at the
  run's pinned version (`models.py:38`-`39`). `FixtureTemplate.checks` (`content/schemas.py:62`);
  `FixtureCheck{action: ProseText, dc: 5–30, success: ProseText, bypassed_by: list[ContentId] = []}` (`:55`-`:59`). `dc` is content's, so `interact` needs no
  range check (`service.py:62`); `success` is prose, nothing flips.
- **Carried vs standing.** Position is `adventure_run_id` + `scene_id` (`models.py:165`-`168`), carriage is
  `owner_object_id` (`:169`). CHECK `carried` (`:142`) forbids owner *and* position; CHECK `position` (`:141`)
  forbids half a position. So `take` = set owner **and** NULL both position columns; `drop` = clear owner **and**
  copy the actor's pair; `give` = rewrite owner alone. Not forbidden by the schema, therefore the service's job:
  taking what another creature owns, taking or giving across scenes, an item with neither owner nor position.
- **Roll consumption, unchanged.** `_consume_roll(run_id, roll_id, kind, turn_id)` (`service.py:791`) wants a
  `roll` of this run, of that `kind`, of that `turn_id` (`None == None`), not already named by an **`ok`**
  `tool_call` of the turn (`_roll_already_spent:774`); it raises and writes nothing, and its caller records the
  refusal and **commits it alone** before re-raising (`_refuse_roll:818`, `_refuse_exit:960`; `append_event` only
  flushes, `:1094`). `interact` calls it with `kind="ability_check"`, never `resolve_check`, whose `tool_call`
  would carry the wrong name.
- **`tool_call` payload** `{name, args, roll_ids→rollIds, result: ok|refused, outcome}` (`schemas.py:188`,
  `extra="forbid"`, stored `by_alias=True`); `args`/`outcome` are free dicts, their keys hand-written camelCase
  (`passive_check`'s `passiveScore`, `:723`).
- **greenhollow.** `village-green`: `mira` carrying `shepherds-knife`, loose `bent-horseshoe`. `lair-maw`: `goblin` ×3,
  `thorn-screen`. `lair-hollow`: `goblin-boss` carrying `notched-cleaver`, `wool-sack` carrying two
  `stolen-fleece`. The seed PC carries `shepherds-knife` (`campaign.json:22`). `thorn-screen` (`:155`-`172`) authors
  two checks: "Lift the lashed brush aside…" dc 13, **no** `bypassed_by`; "Cut through the lashings…" dc 10,
  `bypassed_by: ["shepherds-knife","notched-cleaver"]` — the seed PC passes that one with no roll on day one.
  Characters enter at `village-green`, two free `use_exit` calls from `lair-maw`.

## Work items

All but WI5/WI6 touch `service.py`.
- **WI1 (08a)** the refusal, action-count and carried-item helpers, and the new `ErrorCode`s. *AC1, AC3.*
- **WI2 (08a)** `interact`: the authored check applied by `action`, roll or bypass, three recorded refusals. *AC1.*
- **WI3 (08b)** `take`/`drop`/`give` over the scene and carrier rules. *AC2.* Both need WI1.
- **WI4 (08b)** the `use_item` seam. *AC4.*
- **WI5** each half's `database` acceptance suite (`playthrough_db`; a second connection for refusals, as
  `test_acceptance_rolls_spent_once.py`) · **WI6** the module doc and README. Both parallel to their half's code.

## Interfaces

`async`, `db` first, rest keyword-only, each ending `turn_id: str | None = None`.

- `interact(user_id, actor_id, object_id, action, roll_id=None) -> bool` · `take(user_id, actor_id, item_id)` ·
  `drop(…)` · `give(user_id, from_id, to_id, item_id)` · `use_item(user_id, actor_id, item_id, target_id=None)`
  (always raises); the movers return `None`.
- **Gate order, identical in all five**: `_resolve_actor_and_run` (`:547`) → one-action check → mechanic checks →
  write → `tool_call` `ok` → one commit. Every refusal is a `refused` `tool_call` at `dm`, committed alone, then
  raised (← D11).
- **`args` recorded**: `interact {actorId, objectId, action, rollId?}` · `take`/`drop` `{actorId, itemId}` ·
  `give {actorId, toId, itemId}` (the giver is `actorId`, so one key names the actor) ·
  `use_item {actorId, itemId, targetId?}`. `outcome` on success: `interact {action, dc, total?, bypassedBy?,
  success}`, the others `{}`. `rollIds` is `[roll_id]` for a roll-fed `interact`, else `[]`.
- **One action per turn** = this run's `tool_call` events where `turn_id IS NOT DISTINCT FROM ?`, then
  `payload["result"] == "ok"`, `name in {interact, take, drop, give, use_item, attack}`, `args["actorId"] ==
  actor_id` — `_roll_already_spent:774`'s shape. `attack` is in the set from 08, so parallel sprint 09 needs no
  edit; `use_exit`, rolls and checks are free, and a refusal never spends the turn.
- **Codes** (`core/errors.py:17`; 409): `ACTION_NOT_AVAILABLE` (unknown `action`, or no fixture), `ROLL_REQUIRED`
  (a check needing a roll, none given, nothing bypassing), `ALREADY_ACTED`, `OBJECT_NOT_REACHABLE` (wrong scene,
  owned by another, not carried by the actor, actor unpositioned), `ITEM_NOT_CONSUMABLE`. A wrong-kind or spent
  roll stays `ROLL_NOT_USABLE`, an unknown id `NOT_FOUND`.
- **Consumable is not expressible in content**: `ItemTemplate` is `{id, kind, name, description, attacks}`
  (`content/schemas.py:50`), so `use_item` refuses unconditionally; a later field plus a branch *before* that
  refusal is additive.
- **Bypass** = a row with `owner_object_id = actor.id` and `template_id IN check.bypassed_by`, one query returning
  the id for `outcome.bypassedBy`, consulted only when `roll_id is None`. `action` matches by exact string equality;
  phase 8's tool offers the authored strings verbatim.

## Open questions

- **Product-visible**: `stolen-fleece` sits inside `wool-sack`, so `take` refuses it and Stage-01 can never empty a
  container. Confirm, or let `take` accept an item a **fixture** in the actor's scene owns.
- **Product-visible**: the brief counts `drop` as an action, `decisions/mechanics.md` counts only
  `attack`/`interact`/`use_item`, the SRD drops free — by the brief, take-then-drop costs two turns.
- *Agent-level calls*: only `ok` rows count towards the turn · the one-action check precedes every mechanic check,
  so a second `use_item` answers `ALREADY_ACTED` · an unknown `roll_id` in `interact` is recorded too, the run being
  known already · `interact` enforces reach with `take`'s helper and code (D1's "the exit must be on the current
  scene" in another shape) — drop that branch if AC1's refusals are exhaustive · a failed check is `ok`,
  `success: false`, and spends roll and turn.
- **Untagged turn.** No allocator exists (`turn_id` is a bare column, `models.py:214`), so everything lands in the
  one `NULL` turn and a creature's second action in a run would be refused forever. Tests must mint ids
  (`generate_id()`, no FK) per scenario — AC2's take → drop → give needs three. No route reaches these, so no live
  path breaks.

## The split

**08a — a fixture answers to a check (AC1, AC3)**, WI1 + WI2, verified alone: `thorn-screen` passes on a roll ≥ dc,
passes with no roll for the knife-carrier, refuses an unknown action, a missing roll and a wrong-kind roll, changes
no `objects` row, and refuses that creature's second `interact` in one turn while a new turn allows it.
**08b — an item changes hands (AC2, AC4)**, WI3 + WI4, verified alone: `bent-horseshoe` taken, dropped and given,
refused across scenes and when another owns it, and `use_item` refusing every template. **08b depends on 08a** for
the helpers and codes; nothing flows back, no parallelism is lost. Five mechanics, five codes and two fixtures exceed
one hour; AC3's rule attaches to the first mechanic that must obey it.
