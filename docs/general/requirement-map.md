# Requirement map

How this project satisfies the graded brief. `135.md` at the repository root
is the **only** binding brief; this file maps its requirements onto what the
system does, and nothing else. The design itself is
[app-vision.md](app-vision.md) and [architecture.md](architecture.md).

## Task requirements

| # | Requirement | Covered by |
|---|---|---|
| 1 | Agent purpose, usefulness, target users | [app-vision.md](app-vision.md) — solo AI DM for rule-free entry into pen & paper |
| 2 | Core functionality, primary tasks, user interactions | The game agent and its tools ([architecture.md](architecture.md)); `ask_player` every turn plus the character-generation dialogue |
| 3 | User-friendly UI for **all** functionality | Web client ([architecture.md](architecture.md)); developer settings live in a separate drawer, not the player UI. Read as every **player** capability having a surface — operator capabilities such as content validation are CLI-only by design, since putting developer machinery in the player UI is exactly what optional task Medium-8 penalises |
| 4 | Appropriate tools, error handling, real-world usage | Invalid dice expressions, unknown content ids, state validation, LLM and tool timeouts, checkpoint resume |
| 5 | Documentation: usage, examples, technical decisions | `docs/` — [glossary.md](glossary.md), the adventure authoring guide, the tool reference, and the decision records in [architecture.md](architecture.md) / [model.md](model.md) |

Requirement 2 is also where the agent shape is justified: the game needs
multi-step tool use, durable state and interrupts for player decisions, so a
plain prompt or plain RAG would not do.

## Optional tasks targeted

Aiming for ≥2 medium + 1 hard.

| Brief task | Mechanic |
|---|---|
| Medium 1 — token usage and cost | Per turn and per campaign run, summed from the event stream |
| Medium 2 — long/short-term memory | LangGraph checkpointer (short), journal entries (long) |
| Medium 8 — security guard, dev/user split | Guard node before the agent; developer drawer |
| Hard 1 — agentic RAG | On-demand SRD lookup the agent may re-query |
| Easy 2 — personality | DM tone selectable per campaign run |
| Easy 4 — model settings | Model and temperature in the developer drawer |

Langfuse tracing of every model call (`core/tracing/`, external instance)
covers hard task 2, but is not counted above.
