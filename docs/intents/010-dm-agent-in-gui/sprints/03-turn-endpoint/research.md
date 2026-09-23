---
author: fhit:architect
owner: agent
created: 2026-09-23
---
# Research: sprint 010-03 turn endpoint

## Facts

**How a turn is driven today.** `app game play` resolves the actor from player+run
(`game/commands.py:180-188` → `playthrough_service.get_member_character`, `service.py:588-612`) and
defaults the checkpointer thread to the run id (`commands.py:211`). The loop reads the thread's pending
interrupt with `aget_state` (`commands.py:84-89`), then calls `game/service.py:66 turn(...)` for free words
or `:85 resume(resume_value=...)` for an answer/roll; `build_agent` compiles per call (`service.py:40`),
the saver is `AsyncPostgresSaver` (`core/checkpointer/service.py:49-53`). **Each leg mints a fresh
`turn_id` (`commands.py:43,66)`** — a resumed leg is tagged as a different turn than the one it continues,
which splits both `get_awaiting`'s window and per-turn cost.

**Inside the graph.** `record_action` is the only writer of `player_action`, from the last `HumanMessage`
in thread state (`agent/nodes.py:229-250`); `record_narration` writes the narration with the turn's usage
and flips `ready → active` (`nodes.py:336-368`). `graph.py:29-43`: `load_context → record_action → guard →
narrate ⇄ tools → record_narration`.

**What the run waits for.** `get_awaiting` (`playthrough/service.py:2553-2599`): `_require_member` first;
the open turn is the newest event's `turn_id`; within it, newest `roll_requested` unanswered →
`"roll:<eventId>"`, else newest `question` with no later `player_action` → `"answer:<eventId>"`, else
`"none"`. The interrupt values carry the same ids: `{type:"question", question_id, text, options}`
(`agent/tools.py:295-302`), `{type:"roll_request", request_id, kind, formula, actor_id, context}`
(`tools.py:333-342`).

**Gap:** nothing writes a `player_action` when an interrupt is resumed (only writer: `nodes.py:244`), so a
question stays `"answer:<id>"` for ever and the player's choice never reaches the transcript.

**The roll is always the server's.** After resume the tool itself calls `resolve_roll_request`
(`tools.py:362-368`), which re-uses the stored formula and rolls server-side
(`playthrough/service.py:895-921`); a roll already recorded for that request is not repeated
(`tools.py:344-361`). No caller value reaches dice.

**Refusals already in place.** `_require_member` → `CampaignRunNotFoundError` → `NOT_FOUND` for a foreign
*or* unknown run (`service.py:172-187`, `errors.py:23-31`); `_require_ready_or_active_run` → `RUN_ARCHIVED`
/ `INVALID_RUN_STATUS` (`service.py:800-815`).

**Route conventions.** `CamelModel` on the wire (`core/schemas.py:7`); one envelope and its code table
(`core/errors.py:17-109`); routes map `PlaythroughError → ApiError(exc.code)` and contain no
commit/add/execute (`playthrough/routes.py:46-51`); `CsrfAuth` for writes (`auth/dependencies.py:40-47`);
routers mounted in `api/v1/router.py:10-16`; the typed client is `app openapi export` →
`openapi-typescript` → committed `frontend/src/api/schema.d.ts` (`Makefile:86-88`, stack up).

**langgraph 1.2.11** (`backend/uv.lock:526-527`, source: context7 → docs.langchain.com fault-tolerance /
time-travel): `invoke(None, config)` resumes an interrupted or failed run from its last checkpoint without
new input; `StateSnapshot.next` names the nodes still to run.

**Opening turn (D13).** `enter_adventure` writes only `adventure_started` and leaves run status alone
(`service.py:674-785`); the first narration activates the run anyway (`nodes.py:361-367`). A DM-led turn
still needs a `HumanMessage` to instruct the model (and it is the boundary `_turn_usage` counts from,
`nodes.py:306-333`), so `record_action` needs an explicit off-switch — otherwise it writes a player row.

## Work items

- WI1 backend-python — the turn engine: `game/service.py`, `game/agent/{state,nodes}.py`, `game/errors.py`,
  plus one read in `playthrough/service.py` (I3); exposes `run_turn` (I2) and unit tests.
- WI2 backend-python — the wire: `game/schemas.py`, `game/routes.py`, `api/v1/router.py`, error mapping,
  module README, then `make generate-api` to refresh the committed typed client.
- WI3 qa — black-box acceptance tests AC1–AC6 (`backend/tests/game/`, `TestClient`, monkeypatched
  `game.service.run_turn` / pinned playthrough functions per `tests/conftest.py:1-80`), and AC7's
  measurement (below).

WI2 and WI3 are written against I1 and may run beside WI1.

## Interfaces

**I1 — `POST /api/v1/game/runs/{runId}/turn`**, `CsrfAuth`. Body: `{"text": string | null}` (≤2000 chars)
and nothing else — the caller can name no kind and no number. 200:
`{"turnId": string, "kind": "action"|"answer"|"roll"|"retry"|"opening", "awaiting": "none"|"roll:<id>"|"answer:<id>"}`
(`awaiting` from `get_awaiting` after the turn). Errors: 401 `NOT_AUTHENTICATED`/`SESSION_EXPIRED`,
403 `CSRF_TOKEN_INVALID`, 404 `NOT_FOUND` (not seated, unknown run, no character — AC6), 409
`INVALID_RUN_STATUS` / `RUN_ARCHIVED`, 409 `ACTION_NOT_AVAILABLE` with
`details:{awaiting, options}` (AC2: words that are not one of the offered options while an answer is
awaited), 422 `VALIDATION_ERROR`, 502 `LLM_*` (a broken turn, AC4's precondition), 500 `INTERNAL_ERROR`.

**I2 — `game.service.run_turn(db, *, user_id, run_id, text) -> TurnOutcome(turn_id, kind, awaiting)`**,
raising `PlaythroughError`/`GameError` (both carry `.code`, `.details`). Kind comes from the thread
snapshot and the transcript, never the body, in this order: pending `question` interrupt → `answer` (text
must equal one of the interrupt's `options`, or any text when `options` is empty; else refuse) — writes
`player_action {text, answersQuestionId}` under the open turn, commits, then `resume(text)`; pending
`roll_request` interrupt → `roll`, `resume({"action":"roll"})`, body text discarded (AC3); `next`
non-empty without interrupt → `retry`, `invoke(None)` (AC4); text present → `action`, new `turn_id`;
no text → `opening`, DM-led, no player row (AC5). Resumed kinds reuse the open turn's `turn_id`.

**I3 — supporting signatures.** `playthrough.service.open_turn_id(db, *, user_id, run_id) -> str | None`
(`_require_member` first; the newest event's `turn_id`). `game.service.thread_state(agent, *, thread_id)
-> ThreadState(interrupt: dict | None, pending: bool)`; `game.service.retry(agent, *, thread_id, context)
-> TurnResult`; `DmContext.record_action: bool = True` (`agent/state.py:37`), honoured at `nodes.py:235`.

**AC7 (WI3).** `server: uvicorn` reaches the public host unchanged, so the proxy cannot be read off a
header: ask the host's operator for the configured read timeout, and measure it once — pin
`SSE_POLL_INTERVAL_SECONDS`/`SSE_MAX_LIFETIME_SECONDS` to 280 on the deployed stack and `curl -N
--max-time 290` the existing stream route; it sends no byte, so the moment the connection is cut is the
idle read timeout (no cut → "≥280 s"). Fallback: time three real turns, reported explicitly as a lower
bound. The number goes in `review.md`, flagged when under 120 s.

## Open questions

None product-visible. Technical, agent's call: a request with no text and nothing pending is a DM-led
turn rather than a refusal (this is what sprint 08 will reuse); where checkpoint and transcript disagree,
the checkpoint decides what runs, since only it can be resumed.
