# game

The dungeon master: the LangGraph agent that narrates, interprets free-form
player actions and calls tools for every mechanic. `game` is the agent
layer only — every deterministic mechanic lives in `playthrough.service`
and is reached through the tools here. Nothing in this module rolls a die
or writes an event.

## Owns

- `service.py` — the public surface: `build_agent()` compiles the graph over
  the core chat model and the resolved system prompt; `turn()` runs one
  player message on a thread and returns the reply plus the rolls made.
  `run_turn(db, *, user_id, run_id, text)` (sprint 010/03) is the one entry
  point the HTTP route calls: it decides which of five kinds
  (`action`/`answer`/`roll`/`retry`/`opening`) a turn is from the run's own
  thread state and transcript, never from what the caller claims, and
  returns a `TurnOutcome(turn_id, kind, awaiting)`. The `opening` leg
  (sprint 010/11 round 4, Fault A — ← finding) first checks `get_awaiting`
  itself: no real interrupt is pending and nothing is queued to retry, so
  a non-`"none"` answer there names a stale or dangling request, never the
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
- `run_turn`'s own building blocks are `thread_state()` (the checkpoint's
  pending interrupt, if any, plus whether a next step is queued at all —
  `ThreadState`) and `retry()` (`invoke(None)`, resuming a broken turn from
  its last saved step without repeating it); `playthrough_service.
  open_turn_id` supplies the id a resumed leg reuses instead of minting a
  new one — or, when it answers `None` (the leg that broke wrote no event
  at all, e.g. an opening turn that crashed before its first narration),
  `run_turn` mints one on the spot so the resumed leg, and the
  `TurnOutcome` it returns, always carry a real turn id.
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
