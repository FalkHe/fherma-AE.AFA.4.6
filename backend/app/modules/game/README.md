# game

The dungeon master: the LangGraph agent that narrates, interprets free-form
player actions and calls tools for every mechanic. `game` is the agent
layer only — every deterministic mechanic lives in `playthrough.service`
and is reached through the tools here. Nothing in this module rolls a die
or writes an event.

## Owns

- `service.py` — the public surface: `build_agent()` compiles the new
  five-node flow (`agent/graph.py`'s `build_graph()`) over the core chat
  model. `run_turn(db, *, user_id, run_id, text)` (sprint 010/03, rewired
  onto the new flow in sprint 011/08) is the one entry point the HTTP
  route *and* the CLI `play` command call: it decides which of five kinds
  (`action`/`answer`/`roll`/`retry`/`opening`) a turn is from the run's
  own checkpointed `state["awaiting"]` (an `AwaitingRef`, kind `"roll"` or
  `"choice"`) and `snapshot.next` alone, never from what the caller
  claims, and returns a `TurnOutcome(turn_id, kind, awaiting)`. A `roll`
  resumes with `Command(resume={})`; an `answer` resumes with
  `Command(resume=text)` after checking `text` against the checkpointed
  public `options`; neither writes its own row — the flow's own
  `roll_player`/`accept_choice` operations do that once the resumed graph
  reaches them. `run_turn` calls `flow_nodes.set_runtime(FlowRuntime(db,
  user_id, model))` once per turn before invoking. The `opening` leg
  (sprint 010/11 round 4, Fault A — ← finding) first checks `get_awaiting`
  itself: no `awaiting` is pending and nothing is queued to retry, so a
  non-`"none"` answer there names a stale or dangling request, never the
  player's own — `{text: null}` against it now raises
  `ActionNotAvailableError` rather than silently writing a DM-led filler
  turn.
- `errors.py` — `GameError`, the base every failure `run_turn` raises
  directly carries (`code`, `details`); a `PlaythroughError` raised inside
  `playthrough.service` propagates through unchanged instead.
- `schemas.py` — the turn route's wire shapes: `TurnRequest` (`text` only,
  `extra="forbid"`) and `TurnRead` (`turnId`, `kind`, `awaiting`).
- `routes.py` — `POST /runs/{run_id}/turn`, behind `CsrfAuth`, mapping
  `PlaythroughError`/`GameError` onto the one error envelope.
- `agent/graph.py` — the `StateGraph`: `load_context -> record_action -> guard -> narrate -> (tools -> narrate)* -> record_narration -> END`.
- `agent/nodes.py` — node factories, context hydration, and routing functions.
  `narrate` rebuilds `_turn_mechanics_summary` fresh on every call (sprint
  010/11 round 4, Faults B/C — ← finding: `tool_call attack` recorded
  `hit` while the narration said "fails to connect", and a character at 0
  HP was narrated standing): a "This Turn's Mechanical Results" block,
  read back from this turn's own `tool_call`/`hp_changed`/`roll` events,
  telling the model what actually happened (and flagging any
  `attack`/`damage` roll no matching tool call has consumed yet) before
  it narrates, with an explicit rule not to contradict it.
- `agent/flow_state.py` — sprint 011/05, WI1: the new flow's checkpoint-native
  state (`GameFlowState`, `OperationKind` and its dataclasses) that the old
  graph below does not use yet; `agent/state.py`'s `DmState`/`DmContext`
  still runs the live graph untouched.
- `agent/operations.py` — sprint 011/05, WI2: `OperationContext`,
  `validate_refs` (payload ids checked against `Situation` before any
  service call), `execute_operation` (refuses `stale_reference` first, else
  dispatches) and `OPERATION_HANDLERS`, the merge of this file's own
  player-input/check/combat handlers with `operations_world.WORLD_HANDLERS`.
  Also unused by the live graph yet.
- `agent/operations_world.py` — sprint 011/05, WI3: the world and lifecycle
  handlers (`interact`, item transfer, exits, adventures, hostility, leave
  scene, `RECORD_BEAT`/`COMPLETE_ACTION`/`CLOSE_TURN`/`FINISH_RUN`) that
  `agent/operations.py` folds into `OPERATION_HANDLERS`.
- `agent/state.py` — `DmState`, `DmContext` (session, user, actor, run id, turn id,
  `record_action` —
  what tools need and the model must never supply) and readers.
  `record_action` defaults `True`; `run_turn`'s `opening` leg (sprint
  010/03) sets it `False` so `record_action` (`agent/nodes.py`) writes no
  player row for a turn with no player text. `db_lock` (sprint 010/11
  round 4, Fault A — ← finding) is an `asyncio.Lock` every tool call
  serialises against (`agent/tools.py`'s `_serialized`): `ToolNode` runs a
  batch of tool calls from one `AIMessage` concurrently, but they all
  share this context's one `AsyncSession`, which is not safe for
  concurrent use — two goblins attacking in the same turn corrupted the
  session mid-flush and left a `roll_requested` with no matching `roll`.
- `agent/tools.py` — the tools the DM may call; each is a thin call into
  `playthrough.service` or `content.service`. `roll_dice`, `attack` and
  `damage` accept an `actor_id` that is a real id or, when that lookup
  fails, a creature's own name (`playthrough_service.resolve_actor_ref`,
  sprint 010/10, ← finding); an actor or attack that still can't be
  resolved returns a structured `{status, message, living_creatures}`
  result instead of raising, so the model's next call can name a real id
  — never a bare `"refused: …"`. `get_scene` adds `creatures_present`
  (`playthrough_service.describe_scene_creatures`) when a run is in
  context, the same shape the game context below renders. `roll_dice`'s
  own result carries a `next_step` hint for `kind="attack"/"damage"`
  (sprint 010/11 round 4, Fault B — ← finding: three monster attack rolls
  were made and never followed by `attack`, and the model decided the
  miss itself) — that total alone is never a hit, a miss or damage;
  `attack`/`damage` stay the only tools that decide either.
  `attack` also takes an optional `target_name` (Fault D — ← finding: an
  attack meant for "the nearest goblin raider" landed on the innkeeper,
  AC 10, because `target_id` secretly named her): checked case-
  insensitively against `target_id`'s own resolved name in the current
  scene before any roll is spent, and refused with the creatures-present
  hint on a mismatch rather than silently landing on the wrong creature.
  Every tool is wrapped `@_serialized` (Fault A), which serialises the
  call against `DmContext.db_lock` — applied directly under `@tool(...)`,
  never through `ToolNode`'s own `awrap_tool_call` hook, which swallows
  `ask_player`/`request_player_roll`'s own `interrupt()` into an ordinary
  error message once any `handle_tool_errors` is set (a gap in
  `ToolNode._arun_one` itself, not this module's own logic).
- `prompts/v<n>/system/dm.md` — the DM system prompt, resolved through
  `core/prompts/` as `game/system/dm`.
- `commands.py` — `app game play --user <id> [--run-id <run-id>] [--actor
  <actor-id>] [--thread-id <thread-id>]` for an interactive game loop across
  turns: with a `--run-id` and no `--actor`, the acting hero is resolved from
  the signed-in player's own character on that run
  (`playthrough_service.get_member_character`) -- a run with no character
  yet fails with that lookup's error; `--actor`/`--actor-id` still overrides
  for debugging. The checkpointer thread defaults to the run id, so quitting
  and re-running `play` on the same run rejoins the same thread and any
  question or roll the Dungeon Master was waiting on; `--thread-id`
  overrides that default. `app game graph [-o <path>] [-f <png|mermaid>]`
  inspects or exports the agent's graph visualization.

- `agent/narration.py` — sprint 011/06, WI2: `narrate()`, the new flow's
  separate unbound narration call over `Situation.public()` only (never
  the private `Situation`) plus the accepted player action text and the
  recorded events named by `BeatRequest.allowed_evidence_ids` — no
  `bind_tools`, no database write. Returns a `BeatDraft`; `draft_state()`
  puts it in `state["narrative"]` and it stays there until the
  `RECORD_BEAT` operation (`agent/operations_world.py`) reports `ok`, at
  which point `recorded_state()` clears the draft and sets `event_id`.
  Prompt: `prompts/v1/narration/beat.md`, resolved as
  `game/narration/beat`. Unused by the live graph yet.
- `agent/decisions.py` — sprint 011/06, WI1: `decide()`, one call per
  `DecisionKind` (`read_move`, `interpret_evidence`, `judge_reference`,
  `assess_move`, `monster_action`, `world_reaction`) against its own
  `prompts/v1/decision/*.md` prompt and its own evidence view of
  `Situation` (public for most kinds, the private view for `assess_move`
  and `world_reaction`, which need authored DCs and hidden intent).
  `read_move` and `interpret_evidence` bind exactly `lookup_rule` and
  `recall_history` — fresh closures over the call's own `DecisionContext`,
  never the live graph's `agent/tools.py` — through a plain, ungraphed
  loop capped at `MAX_TOOL_CALLS` (3) total tool calls before the model is
  asked for its structured answer. Every proposed operation kind is
  checked against the strategy's own `allowed_operations`, and every
  named id/attack/choice against `operations.validate_refs`; either
  failure re-prompts under the same `decision_id` up to `RETRY_BUDGET` (2)
  times before `DecisionInvalid` escapes to the caller. Unused by the live
  graph yet.
- `agent/effects.py` — sprint 011/07, WI1: `NextEffect`, the new flow's
  real next-step union (`DecisionRequest | Operation | PlayerWait |
  BeatRequest | TurnComplete`, the first and third re-exported from
  `decisions.py`/`narration.py` unchanged), plus `PlayerWait`,
  `TurnComplete`, `ResumeResult` and `add_usage()`. `flow_state.NextEffect`
  keeps its untyped placeholder to avoid a circular import; this module is
  the one with the real shape. Unused by the live graph yet.
- `agent/advance.py` — sprint 011/07, WI1: `select_next_effect()`, the new
  flow's pure scheduler (`docs/general/game-flow.v2.md`, "Scheduler
  priority") — no model call, no dice, no database write, no `interrupt()`.
  Evaluates `advance_terminal` (hero down/run over → `FINISH_RUN`, ending
  beat, then `TurnComplete`), `advance_hit` (a `pending_hit_id` permits
  only its own damage roll and `APPLY_DAMAGE`), `advance_request` (a
  checkpointed unanswered request → `PlayerWait`), `advance_action` (the
  current `ActionCursor`'s next plan step, a guard refusal straight to
  `RECORD_BEAT`, or a `READ_MOVE` decision for a fresh move), `advance_combat`
  (`eligible_hostiles()` by cursor order, `SETTLE_INITIATIVE` or the next
  hostile's `MONSTER_ACTION`), `advance_reactions`, `advance_narration` and
  `validate_turn_close` in that order, the first non-`None` result winning.
  Also builds the deterministic `player_roll_plan()`/`attack_plan()`/
  `complete_action_plan()` plans decisions turn into `ActionCursor.plan`s,
  and `resume_operation()`, which turns a checkpointed `ResumeResult` into
  its consuming `ROLL_PLAYER`/`ACCEPT_CHOICE` operation or rejects a stale
  `request_id`. `guard_state()` is the one piece of state the caller
  (`agent/flow_nodes.py`) must apply itself, since `advance.py` never
  mutates state: it puts the canned guard refusal into
  `state["narrative"].draft` before the scheduler's `RECORD_BEAT`
  operation runs. Unused by the live graph yet.
- `agent/flow_nodes.py` — sprint 011/07, WI2/WI3: the new flow's five plain
  async node functions (`advance`, `decide`, `execute`, `await_player`,
  `narrate`) and `route_after_advance()`, matching `docs/general/
  game-flow.v2.md`'s five node contracts — not yet composed into a graph
  (sprint 08 does that). Dependencies (`db`, `user_id`, `model`) come from
  a module-level `FlowRuntime` set by `set_runtime()`. `advance` reconciles
  a checkpointed `resume` (via `advance.resume_operation()`) into the
  consuming operation or rejects it, applies a guard refusal's canned text
  (`advance.guard_state()`), then stores one `select_next_effect()` result.
  `decide`/`narrate` accumulate usage through `effects.add_usage()`; a
  `decisions.DecisionInvalid` becomes `state["error"]` rather than an
  exception. `await_player` calls `interrupt()` first and writes nothing
  before it. `GameFlowState` gained a `resume` key (cleared by
  `close_turn_state()`) for the checkpointed response `await_player`
  stores and `advance` consumes. Unused by the live graph yet.

## Surface

- `POST /api/v1/game/runs/{runId}/turn` (sprint 010/03) — the network call
  that runs a turn; wired in `app/api/v1/router.py` under `/game`. Plus the
  CLI below.

## Tools

| Tool | Status |
|---|---|
| `roll_dice(kind, context)` → `playthrough.service.roll` | done |
| `resolve_check`, `resolve_save`, `passive_check`, `roll_initiative` | done |
| `ask_player`, `request_player_roll` (interrupts) | done |
| `interact`, `take`, `drop`, `give`, `use_exit` — typed `MutationResult` refusals surface as `{"status": "refused", "reason": ...}`, `use_item` retired | done |
| `attack`, `damage` | done |
| `recall` | done |
| `lookup_rule` | done |
| `get_scene`, `get_object`, `get_campaign` | done |

## Quirks

- The checkpointer uses `core/checkpointer/service.py` for Postgres session-level persistence, with `InMemorySaver` fallback for isolated unit testing.
- Interrupt tools (`ask_player`, `request_player_roll`) pause turn execution via LangGraph `interrupt()` and resume seamlessly via `Command(resume=...)`.
  A resume re-executes the whole tool coroutine from the top (LangGraph's
  own documented behaviour), so any side effect before the `interrupt()`
  call runs a second time — `request_player_roll`/`resolve_roll_request`
  (`playthrough.service`) are the tools that matter here, and are made
  idempotent there (sprint 010/09, ← finding) rather than in this module.
- `roll_dice` and `request_player_roll` share one `context` shape,
  `tools.RollContext` (sprint 010/09, ← finding): named, described fields
  (`ability`, `skill`, `dc`, `item_id`, `attack`, `expression`) rather than
  a bare `dict[str, Any]`, which gave the model no field names to fill and
  let an empty `{}` reach `dice.derive_formula` as a valid call — the DM
  would then either silently self-roll a player's own check through
  `roll_dice`, or narrate the tool's own expected arguments as chat text
  instead of calling it, and `request_player_roll` never produced a
  pending roll in live play. The system prompt instructs the DM to always
  pass `context={"ability": <lowercase SRD name>, "skill": <skill or
  null>, "dc": <number>}` on `request_player_roll` for ability checks and
  saving throws, and to route every player-character check/save through
  `request_player_roll` rather than self-rolling it via `roll_dice`; the
  tool descriptions repeat the same requirements. `dice.derive_formula`
  also now raises an actionable `ValueError` (naming what is missing)
  rather than a bare `KeyError` when a check/save/custom roll's context is
  still incomplete despite the schema, so a model that gets it wrong once
  can correct itself instead of retrying the same broken call.
- The graph is async end to end because the mechanics are.
- Tests monkeypatch `service.chat_model`, `service.load_prompt` and
  `tools.playthrough_service.roll`; call
  through the module reference, never by name import.
- `narrate` calls the bound model through `core/llm/service.ainvoke_chat()`,
  never `bound.ainvoke()` directly, so a transient provider failure is
  retried quietly and a permanent one raises the classified `LlmError` --
  same as every other model call in the app.
- `record_narration` sums `llm_service.usage_of()` over every `AIMessage`
  since the last `HumanMessage` (the boundary an interrupt survives) and
  passes the total as that turn's narration `usage=`; `playthrough.service`
  stores it and sums it back up per run.
- Sprint 011/03, WI3: this module holds no save of its own — `record_action`
  and `record_narration` (`agent/nodes.py`) and `run_turn`'s own answer leg
  (`service.py`) call `playthrough_service.record_player_action` /
  `record_answer` / `record_narration`, each owning its own transaction
  (including the `ready -> active` activation, now inside
  `record_narration`); no `commit`, `db.add` or `append_event` remains in
  `game/`.
- `lookup_rule` writes a player-visible `rule_looked_up` entry
  (`playthrough_service.record_rule_lookup`, sprint 010/04, I3) only when
  the search actually matched and `ctx.run_id` is set; the entry carries
  the best match's `heading_path`, never the rules text and never the
  model's own query.
- `thread_state()` reads the checkpoint back without invoking the graph —
  `awaiting` straight off `state["awaiting"]`, `pending` off whether a next
  step is queued at all (`ThreadState`); a retry resumes with
  `agent.ainvoke(None, ...)` inline in `run_turn` rather than a separate
  helper. A resume's turn id comes from the checkpointed
  `state["turn"].turn_id`; `playthrough_service.open_turn_id` is the
  fallback when that key is missing (an empty snapshot), and `run_turn`
  mints a fresh id only for a brand-new `action`/`opening` turn.
- `game/commands.py`'s `play` command (sprint 011/08, WI2) drives the same
  `run_turn` the HTTP route calls, one call per turn, and renders whatever
  it just wrote by reading the transcript back
  (`playthrough_service.list_events(after=<cursor>)`) rather than a graph
  return value — narration and rolls through `_print_turn_result`,
  a pending `question`/`roll_requested` row as the same prompts the old
  session printed.
- `agent/nodes.py`'s `_build_game_context` renders the current scene's own
  creatures id first — `id <id>: <name> (<player|monster|npc>), HP …, AC
  …, alive|down, attacks: …` (sprint 010/10, ← finding: several
  identically-named monsters, e.g. three `Goblin Raider`s, were otherwise
  untellable apart, and a monster with no attacks looked no different from
  one that could act) — via `playthrough_service.describe_scene_creatures`,
  the same reader `get_scene` and every combat tool's own lookup-failure
  hint use, so a creature's id, role and attacks read the same everywhere
  the model can see them. `request_player_roll` (`playthrough.service`)
  now refuses an actor that is not the party's own character, a kind that
  is not the player's to roll (attack/damage always go through
  `roll_dice`, for every actor including the hero), and a `custom`
  expression with no dice in it (a bare `"10"` used to render as a "Roll
  10" button with nothing to roll).
