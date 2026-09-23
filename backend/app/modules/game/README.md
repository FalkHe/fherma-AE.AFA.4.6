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
  returns a `TurnOutcome(turn_id, kind, awaiting)`.
- `errors.py` — `GameError`, the base every failure `run_turn` raises
  directly carries (`code`, `details`); a `PlaythroughError` raised inside
  `playthrough.service` propagates through unchanged instead.
- `schemas.py` — the turn route's wire shapes: `TurnRequest` (`text` only,
  `extra="forbid"`) and `TurnRead` (`turnId`, `kind`, `awaiting`).
- `routes.py` — `POST /runs/{run_id}/turn`, behind `CsrfAuth`, mapping
  `PlaythroughError`/`GameError` onto the one error envelope.
- `agent/graph.py` — the `StateGraph`: `load_context -> record_action -> guard -> narrate -> (tools -> narrate)* -> record_narration -> END`.
- `agent/nodes.py` — node factories, context hydration, and routing functions.
- `agent/state.py` — `DmState`, `DmContext` (session, user, actor, run id, turn id,
  `record_action` —
  what tools need and the model must never supply) and readers.
  `record_action` defaults `True`; `run_turn`'s `opening` leg (sprint
  010/03) sets it `False` so `record_action` (`agent/nodes.py`) writes no
  player row for a turn with no player text.
- `agent/tools.py` — the tools the DM may call; each is a thin call into
  `playthrough.service` or `content.service`.
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
| `interact`, `take`, `drop`, `give`, `use_item`, `use_exit` | done |
| `attack`, `damage` | done |
| `recall` | done |
| `lookup_rule` | done |
| `get_scene`, `get_object`, `get_campaign` | done |

## Quirks

- The checkpointer uses `core/checkpointer/service.py` for Postgres session-level persistence, with `InMemorySaver` fallback for isolated unit testing.
- Interrupt tools (`ask_player`, `request_player_roll`) pause turn execution via LangGraph `interrupt()` and resume seamlessly via `Command(resume=...)`.
- The system prompt (sprint 010/09) instructs the DM to always pass
  `context={"ability": <lowercase SRD name>, "skill": <skill or null>, "dc":
  <number>}` on `request_player_roll` for ability checks and saving throws,
  so the free-form `context` already on the wire carries what the play
  screen needs to label and score the roll; the tool description repeats
  the same requirement. Nothing else about the roll request changed.
- The prompt (sprint 010/09 follow-up) makes `request_player_roll` mandatory
  for every player-character ability check or saving throw and forbids also
  calling `roll_dice`/`resolve_check`/`resolve_save` for that same check;
  `roll_dice`, `resolve_check`, `resolve_save` and `passive_check` stay for
  NPC/monster rolls, hidden rolls and damage. `request_player_roll` itself
  already interrupts the turn and waits for the resumed roll, so this was a
  prompt-only fix — the DM never used to call it at all.
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
