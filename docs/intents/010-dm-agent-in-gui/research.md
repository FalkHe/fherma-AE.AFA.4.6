---
author: architect
owner: agent
created: 2026-09-22
updated: 2026-09-22
---
# Research: 010 DM agent in GUI

## Facts

**The agent is finished and headless.** `game/service.py:66` `turn(agent, *, thread_id, context,
player_text) -> TurnResult(reply, rolls, interrupt)`; `resume(...)` at `:85`, `build_agent` at `:40`; all
20 tools live (`game/agent/tools.py:712`). Its only caller is `app game play`
(`game/commands.py:172`) — `api/v1/router.py:9-14` mounts no `game` router.

**A turn persists itself step by step**, each part committed as it happens: `player_action` at its start
(`game/agent/nodes.py:240-248`), each mechanic's own events mid-turn (`playthrough/service.py:1011,839`),
`narration` at its end (`nodes.py:319-327`).

**The transcript is already an API.** `GET /playthrough/campaign/{runId}/events` answers
`{events, awaiting}`, `awaiting` being `"none" | "roll:<id>" | "answer:<id>"` (`routes.py:166-186`);
player-visible types are narration, player_action, roll_requested, roll, question, scene_entered and the
adventure milestones — `tool_call` is DM-only (payloads: `playthrough/schemas.py:227-307`). `GET …/stream`
is a notice-only SSE (poll 2 s, lifetime 300 s — `routes.py:189-242`, `core/settings.py:23-24`), with no
frontend consumer yet.

**Frontend.** `/runs/:runId` shows campaign header, party and adventures (`App.tsx:30`,
`playthrough/routes/RunRoute.tsx`); "Create character" opens the in-development dialog
(`PartySection.tsx:53`) and "Start adventure" is permanently disabled (`AdventuresSection.tsx:11-16`).
No play screen, no chat component. Its design exists
(`docs/design/dnd-app-dashboard-design/project/SessionView.dc.html`): chat log with dm/player/system rows,
dice chip, composer, party rail with live HP/AC.

**Gaps blocking a turn endpoint.** Nothing resolves the caller's character into `DmContext.actor_id`
(`game/agent/state.py:42`; the CLI takes `--actor`), and nothing maps a run to a checkpointer thread
(`playthrough/models.py:44-56`). `activate_campaign_run` (`service.py:579`) has no caller, so a played run
never leaves `ready`. `record_narration` passes no `usage=`, so per-turn cost — graded Medium 1
(`requirement-map.md`) — is never recorded, and the run's own model, temperature and personality columns
(`models.py:49-51`) are read by nothing. `narrate` binds `chat_model()` directly
(`nodes.py:282,291`), bypassing `chat()`'s classification and quiet retry (`core/llm/service.py:154-188`);
per-call timeout 60 s (`llm/service.py:77`).

**009 offers no code**, only a pattern: sprints 02–07 are open (`009/backlog.md`), so its chat API and
page are briefs — one message in, one whole reply out, no streaming (009-D3), a page at the run's address
plus a segment, an in-voice error line with retry.

langgraph 1.2.11 (`backend/uv.lock`): `CompiledStateGraph.astream(input | Command, *, context,
stream_mode)` exists — introspected in `app-cli`, confirmed by context7.

## Options

**A — taking a turn over the network**

| Option | Pro | Con |
|---|---|---|
| A1 Synchronous `POST …/turn`, answering what the game now waits for | reuses everything; one route, the standard error envelope, ordinary tests | the request lives as long as the model does, so a long turn can outrun a proxy read timeout |
| A2 `POST …/turn` answering `text/event-stream`, driven by `astream` | bytes keep flowing, so no idle timeout; steps arrive as they happen | a second transport the client must hand-roll (`EventSource` cannot POST); duplicates the notice stream |
| A3 `202` plus a fire-and-forget task, client polls | returns instantly | a background task in the web process is what "no job runner" forbids; a lost one strands the run |

Recommendation: **A1** — one endpoint taking free text *or* the answer to an open question/roll, picking
`turn` vs `resume` from `get_awaiting` and answering `{turnId, awaiting}`; the transcript is read
separately. Trade-off: no words on screen until the turn ends. Failure: committed events stay, the error
envelope answers, the player retypes. Blast radius: one route in `game`, plus the gaps above.

**B — what the player sees while a turn runs**

| Option | Pro | Con |
|---|---|---|
| B1 Reuse the SSE notice + refetch `…/events` | already built; rolls and questions surface mid-turn, since each tool commits its own event; one render path for live play and for resuming | ~2 s lag; no word-by-word narration |
| B2 Token streaming of the narration | immediate | needs A2; contradicts 009-D3 |

Recommendation: **B1**, plus a "the DM is thinking" line while the request is in flight.

**C — resuming a session, and the checkpointer thread**

| Option | Pro | Con |
|---|---|---|
| C1 Thread id *is* the run id | no storage, no lifecycle; a pending question survives a closed browser, so `awaiting` and the paused graph cannot disagree | history grows for the life of the run |
| C2 Thread-id column, new thread per session | bounded history; `load_context` rehydrates anyway | a migration, and an interrupt stranded on the old thread while `awaiting` still says the run waits |

Recommendation: **C1** (009/05's client-held id is worse: a reload strands the question).

## Risk

A turn is several model calls, 60 s each possible, behind a proxy whose read timeout is unknown. With no
job runner the turn *is* the request: it holds a worker and a database session throughout, and a cut
connection costs the narration although rolls and questions are already recorded. Hence: the transcript,
never the response body, is the truth.

## Open questions

*Product-visible*

1. Is a wait with dice and questions appearing as they happen enough, or must the narration appear as it
   is written? How long may a turn take before the player is told something is wrong?
2. What does a turn that fails halfway look like — an apology in the Dungeon Master's voice with a retry,
   or a plain error line? (Asked in 008, never answered.)
3. Does the player answer a question or a requested roll in the same message box, or with choice buttons
   and a dice button as the design shows?
4. Does play open as its own screen or replace the run screen, and where does "Start adventure" live now?
5. Should the party rail show live health and armour, as the design does? No read exists for that yet.
6. Does the developer drawer (turn cost, model, tone) belong to this intent?
7. If the player leaves mid-turn, is that turn continued when they return, or dropped?

*Technical (my assumptions)*

- Thread id = run id; no migration, no session concept.
- The turn route resolves the caller's character as the acting creature.
- The first narration flips the run to `active`; `record_narration` records usage, so cost exists, and
  `narrate` moves onto the retry and classification the LLM seam already has.
- Unverified, and to be measured before A1 is committed to: whether a client disconnect cancels the
  handler, and what read timeout the public host's proxy enforces.
