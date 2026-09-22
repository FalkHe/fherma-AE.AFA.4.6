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
- `agent/graph.py` — the `StateGraph`: `narrate -> (tools -> narrate)* -> END`.
- `agent/nodes.py` — node factories and routing functions.
- `agent/state.py` — `DmState`, `DmContext` (session, user, actor, turn id —
  what tools need and the model must never supply) and readers.
- `agent/tools.py` — the tools the DM may call; each is a thin call into
  `playthrough.service`.
- `prompts/v<n>/system/dm.md` — the DM system prompt, resolved through
  `core/prompts/` as `game/system/dm`.
- `commands.py` — `app game turn <actor-id> "<text>" --user <id>` for a
  manual smoke run against a real run.

## Surface

- CLI only. No HTTP route yet.

## Tools

| Tool | Status |
|---|---|
| `roll_dice(kind, context)` → `playthrough.service.roll` | done |
| `lookup_rule`, `get_scene`, `get_monster`, `update_object` | not yet |

## Quirks

- The checkpointer is `InMemorySaver`: a thread lives as long as the compiled
  agent object. The Postgres checkpointer in `core/checkpointer/` is wired in
  a later step.
- No guard node and no `ask_player` interrupt yet.
- The graph is async end to end because the mechanics are.
- Tests monkeypatch `service.chat_model`, `service.load_prompt` and
  `tools.playthrough_service.roll`; call
  through the module reference, never by name import.
