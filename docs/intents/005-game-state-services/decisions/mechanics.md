---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-17
updated: 2026-09-21
stage: approved
---
# Attachment: the mechanics surface

The list of things that may change game state, and nothing else may. Each row is one function in
`playthrough.service`; phase 8 binds each to one agent tool of the same name and adds the LLM-facing description
and the run-state gate. The service enforces the *rule*; the tool prevents the *mistake* (← D1, D2).

Legend: **⏸** the phase-8 tool interrupts the graph and waits for the player · **roll** the mechanic consumes a
roll-result id of that `kind` (← D5) · every row appends at least one `tool_call` event.

## Lifecycle (routes, not tools)

| Function | Writes | Notes |
|---|---|---|
| `start_campaign_run(user, campaign_id)` | `campaign_runs` (`setup`) + owner member + eager `objects` for every adventure | pins `content_version` (← 003-D7); `POST /playthrough/campaign` |
| `create_character(user, run, sheet)` | one creature `objects` row with `member_id`, `template_id NULL`; run → `ready` | the only caller of the generic object write (← D4); seed character until phase 7 |
| `rename / archive / unarchive` | `title`; `status` active↔archived | ← 003-D3, D11 |
| `enter_adventure(user, run)` | `adventure_runs` insert + place that adventure's cast + place the characters in `entry_scene` + `adventure_started` | next id in `campaign.adventures[]`; refused while one is active; `POST /playthrough/campaign/{id}/adventure` |
| `activate_campaign_run` | `status` ready → active | called by the first narration event (phase 8's intro) |
| `finish_campaign_run` | `status` → finished | called by `use_exit` on the last adventure's ending exit only (← D3, D8) |

## Player interaction

| Mechanic | Args | Does |
|---|---|---|
| `request_player_roll` ⏸ | `kind, actor_id, context{target_id?, item_id?, ability?, skill?}` | derives the formula (← D6), appends `roll_requested`; the click resolves it |
| `resolve_roll_request(request_id)` | — | server RNG, appends `roll` linked to the request; `POST /playthrough/campaign/{id}/roll/{requestId}` |
| `ask_player` ⏸ | `question, options?` | appends `question`; the next `player_action` answers it |

## Dice without the player

| Mechanic | Args | Does |
|---|---|---|
| `roll` | `kind, actor_id, context, visibility` | same derivation, rolled now; creatures' attacks, hidden saves |
| `passive_check` | `actor_id, ability, dc` | `10 + modifier ≥ dc`, hidden event, no die — no tell (← glossary) |

`kind ∈ attack · damage · ability_check · saving_throw · initiative · custom`.

## Checks

| Mechanic | Args | roll | Does |
|---|---|---|---|
| `resolve_check` | `roll_id, dc` | ability_check | `total ≥ dc`; the DC is the DM's call, 5–30 |
| `resolve_save` | `roll_id, dc` | saving_throw | same for saving throws |

## Objects and inventory

| Mechanic | Args | roll | Does |
|---|---|---|---|
| `interact` | `actor_id, object_id, action, roll_id?` | ability_check | applies a `FixtureCheck` by its `action`: needs a roll ≥ `dc` unless a carried item in `bypassed_by`; records success. Outcome text (`success`) is prose for the DM — no object state flips in Stage-01 |
| `take` / `drop` | `actor_id, item_id` | — | `owner_object_id` ↔ position; same scene required |
| `give` | `from_id, to_id, item_id` | — | both creatures in one scene |
| `use_item` | `actor_id, item_id, target_id?` | — | consumable effects — none authored yet; ships as the seam only |

No `set_hp`, no `set_state`, no `create_object`, no `reveal`: scene secrets are prose (`Scene.hidden`), resolved by a
check and narrated, remembered by phase 6's journal.

## Combat (← D7: no encounter, no turn pointer)

| Mechanic | Args | roll | Does |
|---|---|---|---|
| `attack` | `actor_id, target_id, item_id, roll_id` | attack | `total ≥ target AC` → hit / miss / crit (nat 20); refused if the actor already acted this turn |
| `damage` | `target_id, roll_id, hit_id` | damage | applies the damage roll to the hit it belongs to; clamps at 0; sets `is_alive=false` at 0 for creatures without a member, `down` state for characters |
| `roll_initiative` | `side_a_ids[], side_b_ids[]` | — | one `roll(initiative)` per side (the player's via ⏸), result narrated; nothing stored beyond the events |

Creature attacks use `roll` + `attack` + `damage` with no interrupt. "One action per creature per turn" is a count of
that creature's `attack` / `interact` / `use_item` `tool_call` events with the current `turn_id`.

## Navigation

| Mechanic | Args | Does |
|---|---|---|
| `use_exit` | `actor_id, exit_id` | the exit must be on the actor's current scene (`load_scene`). `kind=scene` → move (003 T8) + `scene_entered`. `kind=adventure_end` → adventure run `completed` + `adventure_completed`; last adventure → campaign run `finished` (← D8) |

## Memory and rules (phases 4 and 6, listed for the complete picture)

`lookup_rule(query)` · `recall(query)` · `inspect_object(id)` · `get_sheet(actor_id)` — reads, all of them:
nothing in this section writes. `recall(query)` is the DM's long-term memory — it searches the run's past
narration by meaning. There is no fact-writing tool (← 006-D1, D2).

## Shapes carried in `events.payload`

```
roll_requested { kind, actor_id, formula, context }
roll           { request_id?, kind, actor_id, formula, faces[], modifier, total }
tool_call      { name, args, roll_ids[], result: ok | refused, outcome{…} }
question       { text, options[] }
player_action  { text, answers_question_id? }
scene_entered  { adventure_run_id, scene_id }      adventure_started / adventure_completed { adventure_run_id }
```

A roll is *consumed* when a `tool_call` in the same `turn_id` names it in `roll_ids`; the check is a scan of the
open turn's events, never a column. The `awaiting` state of a run is the last open turn's `roll_requested` without
its `roll`, or `question` without its `player_action`.
