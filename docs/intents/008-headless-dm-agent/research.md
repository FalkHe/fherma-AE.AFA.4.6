---
author: architect
owner: agent
created: 2026-09-22
updated: 2026-09-22
status: WIP
---
# Research: intent 008 — headless DM agent

## Facts

**Every mechanic the agent must call already exists** in
`backend/app/modules/playthrough/service.py`, each taking the acting user, ids
and never a number the DM typed (← 005-D2/D6): `request_player_roll:644`,
`resolve_roll_request:666`, `roll:682`, `roll_initiative:746`,
`passive_check:774`, `ask_player:812`, `resolve_check:1036`,
`resolve_save:1053`, `use_exit:1097`, `interact:1242`, `take:1491`,
`drop:1556`, `give:1607`, `use_item:1684`, `attack:1780`, `damage:2016`,
`activate_campaign_run:401`, `append_event:2129` (sole writer of `events`),
`get_awaiting:2275`, `recap:2387`, `recall:2418`. Content reads:
`content/service.py:76,356,388` (`load_campaign`, `load_scene`,
`load_object_template`). No mechanic has an HTTP route — the module README
states outright that the DM tool layer is their only intended caller.

**Memory exists.** Narration is embedded on write (`append_event:2129`);
`recall` searches a whole run by meaning, `recap` by recency (← 006-D1/D3/D5).

**The LLM seam** is `core/llm/service.py`: `chat_model:119` returns a
`BaseChatModel` (so `.bind_tools` works), `chat:154` / `chat_stream:191` add
failure classification and quiet retry (`core/llm/retry.py:113`), `usage_of:243`
yields tokens + USD. Only `chat`/`chat_stream` carry the retry and
finish-reason handling, and neither accepts tools — a graph binding
`chat_model()` directly loses both.

**Persistence plumbing exists.** `core/checkpointer/service.py:49` yields an
`AsyncPostgresSaver` in its own schema, Alembic untouched;
`core/checkpointer/demo_graph.py` proves interrupt-and-resume across two
processes and is explicitly throwaway, to be deleted by this intent.

**Tracing exists.** `core/tracing/service.py:182` `langchain_config(name)`
returns the `config=` dict with a Langfuse `CallbackHandler`; passing it to
`graph.ainvoke(..., config=...)` is the documented LangGraph integration.
`observe:215` nests spans. (langfuse 4.15.4 — context7.)

**Installed, verified by introspection in `app-cli`** (langgraph 1.2.11,
langchain 1.4.2 — local): `langchain.agents.create_agent(model, tools, *,
system_prompt, middleware, state_schema, context_schema, checkpointer)`;
`langgraph.prebuilt.{ToolNode, ToolRuntime, tools_condition, InjectedState}`;
`langgraph.types.{interrupt, Command}`; middleware including
`HumanInTheLoopMiddleware`, `ModelRetryMiddleware`, `ToolErrorMiddleware`,
`SummarizationMiddleware`, `ModelCallLimitMiddleware`, `before_model` /
`after_model` decorators. `ToolRuntime` is how a tool receives per-call
context (session, run id, user id) instead of closing over it.

**Missing.** (1) *SRD retrieval does not exist* — `srd/service.py` has only
`check_vector_width:10`, `corpus_status:23`, `require_corpus:44`; ingest and
search are intent 004 sprints 02–06, still `open` in its `backlog.md`. The
graded RAG criterion cannot be met by this intent alone. (2) `modules/game/`
contains nothing but `prompts/v1/system/smoke.md`, a fixture disclaiming
itself. (3) No DM prompt, no guard node, no turn id is minted anywhere
(`events.turn_id` has no writer outside tests).

## Options

| Option | Pro | Con |
|---|---|---|
| **A** One prebuilt tool-calling loop (`create_agent`) with the mechanics as tools, checkpointed, `ask_player` as an interrupt | Smallest surface; nothing hand-written between model and tools; tool docstrings are the whole contract; streaming, interrupt, resume and Langfuse all come for free | Guard, turn bookkeeping and cost accounting have nowhere to live except inside tools; no enforced order, so nothing stops narration before a roll resolves |
| **B** Hand-built `StateGraph` with explicit phases (interpret → lookup → roll → resolve → narrate → persist) | Every phase is separately testable and separately traced; ordering is structural | Many nodes and edges for a turn whose real shape the model decides anyway; every phase costs its own model call; fights the agentic-RAG criterion, which requires the *agent* to choose whether to look a rule up (← 004-D7) |
| **C** A's loop, with the non-model concerns as middleware around it: `before_model` guard, `after_model` cost/event write, `HumanInTheLoopMiddleware`/`interrupt` for `ask_player`, retry middleware restoring what `chat_model()` lacks | Same small surface as A, but guard, cost and error handling sit in one named place each instead of inside tools; middleware is unit-testable without a model | One more concept to learn; middleware ordering is a real thing to get wrong |

Recommendation: **C** — the mechanics are already the safety layer
(← 005-D1), so the graph's only job is the loop plus the four cross-cutting
concerns, and each of those is a named middleware rather than a node.

Turn persistence in all three: `events` is the timeline, the checkpointer is
derived plumbing never shown (← 005-D9); `thread_id` is scoped to an active play
session, while `campaign_run_id` owns the long-term database state and event transcript.
Starting a new session or resuming an adventure creates a session thread and hydrates
context via `load_context` from the database (scene, creatures, objects, recap).
Blast radius stays inside `modules/game`
plus one CLI group; failure behaviour is a `tool_call … result: "refused"` or
an `error` event, both already recorded and player-invisible (← 005-D11).
Trade-off accepted: the model, not the graph, decides turn order.

## Open questions

Product-visible:

1. How is a turn taken without a screen — one command that plays a turn and
   prints what happened, an endpoint a later screen will reuse, or both?
2. When the game needs the player to decide or to roll, does the turn stop
   and hand back the question, or does it wait to be answered in place?
3. What does the player see of a turn that fails halfway — nothing, a
   retry, or an apology in the fiction?
4. May the DM ask a clarifying question about a vague action, or must it
   always act on a best reading?
5. Does a fight get handled this intent, or is any attack narrated and
   resolved as an ordinary action for now?
6. When a run is picked up again days later, is the DM handed a recap of the
   last few narrations, or does it start cold and search when it needs to?
7. The rules lookup has nothing to search yet — does 008 wait for the rules
   knowledge base to be finished, or ship with rule lookups disabled and the
   DM told to say when it does not know?

Technical (assumptions I would make):

- New module `modules/game/` owning graph, tools, prompts; imports
  `playthrough.service`, `content.service`, `srd.service` only (← 003-D14).
- One tool per mechanic, same name and arguments; context (session, run id,
  user id) arrives through `ToolRuntime`, never as model-supplied arguments.
- `create_agent` with a `context_schema`, not a hand-built `StateGraph`.
- `ask_player` becomes a LangGraph `interrupt`; resume is `Command(resume=…)`
  on the same `thread_id`.
- Retry and failure classification restored over the tool-bound model via
  middleware, so the graph keeps `chat`'s behaviour (← 001-D2/D6).
- `turn_id` is a ULID minted per turn by the graph and passed to every
  mechanic, which is what makes one-action-per-turn and single roll
  consumption work.
- `demo_graph.py` and `smoke.md` deleted once the real graph lands.
