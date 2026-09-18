---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-17
updated: 2026-09-18
stage: approved
---
# Decisions

One line each. `→ file` links an attachment in `decisions/`.

- D1: The service layer carries no rejection mechanism. We control which method is called when, so a service is not
  written to defend against an illegal write arriving from outside its intended path. The controlling layer is the
  agent tool layer: tools are built so the agent cannot make a mistake in the first place. This supersedes the phase
  text "rejects an illegal write" and "Prove … rejection by test" for the service layer — those belong to the tool
  layer, built in phase 8. A game rule (a roll consumed once, one action per creature per turn, the exit must be on the
  current scene) is not a defence: it is the mechanic itself and lives in the service.
- D2: The DM never writes state. Every state change is a named mechanic in `playthrough.service` that takes object ids
  and roll-result ids — never a number the agent typed. There is no agent-facing `write_object`; the generic object
  write exists only inside the lifecycle (character creation). → [mechanics.md](decisions/mechanics.md)
- D3: Lifecycle is explicit and two-level. `POST /playthrough/campaign` creates a campaign run in `setup` (row exists,
  objects or characters still missing); creating the character moves it to `ready` (everything required is in place);
  the first narration moves it to `active`. `POST /playthrough/campaign/{id}/adventure` enters the next adventure in
  `campaign.adventures[]` order and places its cast. Nothing is entered automatically, neither the first adventure nor
  the next. Completing the last adventure sets the campaign run `finished`. 003 landed with `active | archived | finished`, so this phase ships migration `0007` widening the CHECK to
  `setup | ready | active | archived | finished` with default `setup` (research §A1).
- D4: Character creation is its own graph, chat and UI (phase 7). Phase 5 ships `create_character(run, member, sheet)`
  as the single caller of the generic object write; until phase 7 lands it is fed from the campaign's seed character.
  It moves the run from `setup` to `ready`.
  A generated character has no template, so migration `0007` makes `objects.template_id` nullable (research §A2).
  The seed is scaffolding, not a product feature; its retirement is handed to phase 7 (backlog → Proposals).
- D5: Roll results are first-class and live in the event stream: a `roll_requested` event asks, a `roll` event
  answers, and a mechanic consumes a roll by its event id — at most once, only in the turn it was rolled, only when its
  `kind` matches. The player's click on `POST /playthrough/campaign/{id}/roll/{requestId}` triggers server RNG and
  adds no entropy; creature and hidden rolls are rolled by the server inside the mechanic.
- D6: The server derives every formula from `kind` + actor: attack → item `to_hit`, damage → item `damage`, ability
  check and saving throw → ability modifier, initiative → Dexterity modifier, `custom` → an explicit expression that no
  combat mechanic accepts. The DC (5–30) is the one number the DM picks; AC and HP are never arguments.
- D7: Combat in Stage-01 is events-only and has no encounter row (upholds 003-D8). A round is one player turn
  (`turn_id`); each creature takes at most one action per turn, counted over that turn's `tool_call` events;
  initiative is one `roll` per side when hostilities start, narrated and not stored; a fight has nothing to open or
  close. `attack` / `damage` are ordinary mechanics that work in any scene — an ambush is just an attack in exploration.
- D8: Scene change and adventure end are one mechanic, `use_exit(actor, exit)`. The exit must exist on the actor's
  current scene; an exit of kind `adventure_end` completes the adventure run and, for the last adventure, finishes the
  campaign run. Replaces 003 ASSUMPTION 4 (completion on entering a no-exit scene) and needs `Exit.kind` in the
  content schema plus an ending exit on `lair-hollow` — a content-module change owned by this phase (research §B1). Exit conditions and fixture outcomes stay prose — DM judgment.
- D9: The event stream is the only timeline; the agent's message history (checkpointer) is derived plumbing that is
  never shown. Event types: `narration player_action roll_requested roll question tool_call scene_entered
  adventure_started adventure_completed system error warning` — 003 landed the five of ASSUMPTION 12, so migration `0007` swaps the CHECK (research §A3). A pending interrupt (`awaiting: roll | answer`) is derived from the open turn's events; no stored cursor
  (upholds 003-D5).
- D10: Reads are `GET /playthrough/campaign/{id}/events?after=<id>` at visibility `player`, plus one SSE stream per
  campaign run that emits only `{"type":"updated","id":…}`; the client refetches. The stream polls `max(id)` on a
  short interval — no background runner, no LISTEN/NOTIFY.
- D11: A visible roll shows kind, each die, modifier and total; pass/fail appears on the mechanic's `tool_call` event
  that consumed it, not on the roll. A refused mechanic is recorded as a `tool_call` event with `result: refused` at
  visibility `dm`, so the player sees no gap.
- D12: Access: every service function takes the acting `user_id` and checks membership first (research B1
  authoritative, B3 for route ergonomics); an unknown or foreign run answers `NOT_FOUND`. Write mechanics require the
  campaign run to be `ready` or `active`, and the first narration sets `active`; an archived run can be listed and read, not played. The list shows archived runs.
- D13: Dice are stdlib `random` behind an `_rng()` seam in `playthrough/dice.py` (research D1). Each `roll` event
  stores the faces, modifier and total, so replay needs no seed and no new column.
- D14: Cost is `SUM(cost_usd)` over `events`, read by the owner through a membership-gated service function and shown
  only in the developer drawer (upholds 003-D4). The turn itself belongs to phase 8; phase 5 ships the mechanics it
  calls, the event append and the reads above.
