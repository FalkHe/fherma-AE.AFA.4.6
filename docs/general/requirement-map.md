# Requirement map

How this project satisfies the graded brief. `135.md` at the repository root
is the **only** binding brief; this file maps its requirements onto what the
system does, and nothing else. The design itself is
[app-vision.md](app-vision.md) and [architecture.md](architecture.md).

## Task requirements

| # | Requirement | Covered by |
|---|---|---|
| 1 | Agent purpose, usefulness, target users | [app-vision.md](app-vision.md) — solo AI DM for rule-free entry into pen & paper |
| 2 | Core functionality, primary tasks, user interactions | The five-node game flow and typed operations ([architecture.md](architecture.md)); `await_player` for rolls and choices plus the character-generation dialogue |
| 3 | User-friendly UI for **all** functionality | Web client ([architecture.md](architecture.md)). Read as every **player** capability having a surface — operator capabilities such as content validation and cost reporting are CLI-only by design, since putting developer machinery in the player UI is exactly what optional task Medium-8 penalises |
| 4 | Appropriate tools, error handling, real-world usage | Invalid dice expressions, unknown content ids, state validation, LLM and tool timeouts, checkpoint resume |
| 5 | Documentation: usage, examples, technical decisions | `docs/` — [app-vision.md](app-vision.md) and [architecture.md](architecture.md) for what the system is, [game-flow.v2.md](game-flow.v2.md) and its [examples](game-flow.v2.examples.md) for the loop and its operations, [model.md](model.md) for the data model and the decisions behind it, [glossary.md](glossary.md) for the vocabulary, and [modules/content.md](../modules/content.md) for the adventure authoring guide |

Requirement 2 is also where the agent shape is justified: the game needs
multi-step tool use, durable state and interrupts for player decisions, so a
plain prompt or plain RAG would not do.

## Optional tasks targeted

Aiming for ≥2 medium + 1 hard; four medium and two hard are in place, plus
one easy. Medium 1 is counted with its caveat: it is operator-side only.

| Brief task | Mechanic |
|---|---|
| Medium 1 — token usage and cost | Counted, not shown to players: `prompt_tokens`, `completion_tokens` and `cost_usd` are written onto every model-backed event, and `app playthrough cost` totals a run whole and by turn. Operator-side only — no route and no player surface |
| Medium 2 — long/short-term memory | LangGraph checkpointer (short), narration search by meaning (long), the latter reachable by the model itself as `recall_history` |
| Medium 4 — authentication and personalisation | Session auth with CSRF (`modules/auth`); campaign runs, characters and events are owner-scoped, so a player only ever sees their own game |
| Medium 8 — security guard, dev/user split | Structural by design, not a wordlist. The model may only emit validated registry operations and `playthrough.service` alone writes state and rolls, so neither player nor model can change hit points, gold or items outside the rules. Player text never reaches a model reply directly: it enters as evidence in a typed decision and leaves as a structured one that `advance`/`execute` must accept before `narrate` speaks. Session auth and CSRF bound each run to its owner; model and prompt settings are operator-side (`.env`, `modules/<module>/prompts/`) |
| Hard 1 — agentic RAG | Two read-only tools inside `decide` — `lookup_rule` over the SRD corpus and `recall_history` over past narration — bound only for the decision strategies that set `binds_tools`, capped at three calls per decision, after which the model must give its structured answer |
| Hard 2 — LLM observability | Langfuse tracing of every model call (`core/tracing/`, external instance); blank `LANGFUSE_*` variables simply run without it |
| Easy 2 — personality | Two authored voices, both fixed in the prompt files and always in character: the Tavern Keeper who runs character creation (`character/prompts/v1/system/creator.md` — warm, dry-witted, never breaks character to mention being a model, never states a number the tools did not give it) and the narrating DM (`game/prompts/v1/narration/beat.md` — two to five sentences of vivid second-person present tense, per beat kind). What the brief's "based on user needs" half would add — a tone the player picks per campaign run — is not implemented |
