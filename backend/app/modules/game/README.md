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
- `agent/graph.py` — the `StateGraph`: `load_context -> record_action -> narrate -> (tools -> narrate)* -> record_narration -> END`.
- `agent/nodes.py` — node factories, context hydration, and routing functions.
- `agent/state.py` — `DmState`, `DmContext` (session, user, actor, run id, turn id —
  what tools need and the model must never supply) and readers.
- `agent/tools.py` — the tools the DM may call; each is a thin call into
  `playthrough.service` or `content.service`.
- `prompts/v<n>/system/dm.md` — the DM system prompt, resolved through
  `core/prompts/` as `game/system/dm`.
- `commands.py` — `app game play --user <id> [--run-id <run-id>]` for an
  interactive game loop across turns.

## Surface

- CLI only. No HTTP route yet.

## Tools

| Tool | Status |
|---|---|
| `roll_dice(kind, context)` → `playthrough.service.roll` | done |
| `resolve_check`, `resolve_save`, `passive_check`, `roll_initiative` | done |
| `ask_player`, `request_player_roll` (interrupts) | done |
| `interact`, `take`, `drop`, `give`, `use_item`, `use_exit` | done |
| `get_scene`, `get_object`, `get_campaign` | done |
| `lookup_rule`, `update_object` | not yet |

## Quirks

- The checkpointer uses `core/checkpointer/service.py` for Postgres session-level persistence, with `InMemorySaver` fallback for isolated unit testing.
- Interrupt tools (`ask_player`, `request_player_roll`) pause turn execution via LangGraph `interrupt()` and resume seamlessly via `Command(resume=...)`.
- The graph is async end to end because the mechanics are.
- Tests monkeypatch `service.chat_model`, `service.load_prompt` and
  `tools.playthrough_service.roll`; call
  through the module reference, never by name import.
