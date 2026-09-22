---
author: architect
owner: agent
created: 2026-09-22
---
# Research: Sprint 009-05 — the creation conversation over the network

## Facts

- `service.build_creation_agent` (`backend/app/modules/character/service.py:203`) defaults to
  `InMemorySaver()` **per call**; `service.turn` (`:222`) takes `thread_id` + `CreationContext` and
  returns `CreationTurn(reply, saved)` (`:197`). All conversation state lives in the checkpointer.
- The CLI builds one agent and one uuid thread per process (`character/commands.py:105`), no Postgres
  saver (`:12`). `game/commands.py:79` is the only Postgres-saver caller and there is no `game/routes.py`
  — this is the first agent behind HTTP.
- Draft keys the tools write: `race`/`character_class`, `name`/`appearance`/`backstory`,
  `abilities`+`rolled`, `skills`, `alignment`, `equipment_pick_<i>` (`agent/tools.py:108-326`).
  `take_default_equipment` (`:329`) writes nothing. A sheet builds from race+class+name alone
  (`_REQUIRED_DRAFT_FIELDS`, `tools.py:38`; `_request_from_draft` `:57` fills scores, alignment and
  equipment defaults), so `canSave` turns true early — it cannot drive the step indicator.
- `playthrough.service.get_run_overview` (`playthrough/service.py:373`) already returns, in one call,
  membership (`CampaignRunNotFoundError` → 404 for foreign *and* unknown, `playthrough/errors.py:23`),
  `campaign_id`/`content_version`, `unavailable`, and members with `ready = has character`
  (`playthrough/schemas.py:49`). `CHARACTER_EXISTS` is 409 (`core/errors.py:67`).
- Route precedent: `CsrfAuth` on writes, `except PlaythroughError as exc: raise ApiError(exc.code)`
  (`playthrough/routes.py:42-127`). Router registration: `app/api/v1/router.py:10`.
- Tests: a fresh `create_app()` per test with a stubbed db session (`tests/conftest.py:77`), services
  monkeypatched; scripted-model precedent `tests/character/test_creation_agent.py:33`; acceptance
  precedent `tests/playthrough/test_acceptance_character_and_shelf_life.py`.
- `make generate-api` = `app openapi export` + `openapi-typescript` (`Makefile:86`). One uvicorn process,
  `--reload` (`compose.yaml:14`). langgraph 1.2.11 (`backend/uv.lock:526`) — this sprint adds no
  unused-before API (`ainvoke`/`aget_state` already in `service.turn`), so no external doc rests on it.

## Decisions (technical)

1. **State between requests**: one agent per FastAPI app, built lazily on `app.state` from
   `build_creation_agent()` (default `InMemorySaver`), plus `app.state` dict
   `conversationId → (run_id, user_id, seed, ready_made_items, last_draft)`. Start mints an opaque
   `generate_id()` used verbatim as `thread_id`; nothing is derived from client input and nothing is
   persisted. Trade-off: a restart (`--reload` on every edit), a crash or a second worker loses live
   conversations — the player starts over, which D12 allows; blast radius is one conversation. Postgres
   checkpointing is rejected: a table, a setup step and rows nobody ever reads again.
2. **Run/user never come from the client**: they are read from the stored record; every message
   re-checks membership through `get_run_overview`, and a record whose `user_id` is not the caller's
   answers 404 like any foreign id.
3. **Sheet so far**: `CreationTurn` gains `draft: dict` (one line — `ainvoke` already returns it), and a
   pure `service.creation_progress(draft) -> CreationProgress(sheet, step, can_save)` renders it.
   Derived numbers (`maxHp`, `armourClass`, `speed`, `skills`, `equipment`) come only from a successful
   `build_sheet`; everything else straight from the draft, nulls elsewhere. `canSave` = the build
   succeeded. `step` = first unreached of the seven; `take_default_equipment` starts writing
   `{"equipment_defaults": True}` so the equipment step can complete (5 lines in `tools.py`).
4. **Model failure**: the turn is wrapped exactly as the CLI wraps it (`commands.py:130`) — any
   exception answers **200** with `reply` = the in-voice line, `error: true`, and the previous
   `sheet`/`step` from the stored draft, so the page shows it inline and offers "Try again" (D14 §1.17).
   `MODEL_ERROR_REPLY` moves from `commands.py:32` to `service.py`; both callers import it. 4xx refusals
   stay the shared envelope.
5. **Saving** stays the agent's `save_character` tool; `saved: true` tells the page to refetch the run.
   `POST /playthrough/campaign/{runId}/character` is untouched, and no rolled-score request type is
   added — the agent builds the sheet, the web never submits scores (sprint 04 issue closed).

## Work items

- WI1 (backend-python): `character/routes.py` + schemas + the three service/tool edits above, mounted in
  `api/v1/router.py`, README surface updated, plus `tests/character/test_routes.py` (one test per AC) and
  the `scripted_model` fixture below.
- WI2 (same agent, after WI1): `make generate-api`, commit `frontend/openapi.json` +
  `frontend/src/api/schema.d.ts`, `make frontend-typecheck`.
- qa (parallel, against the interfaces): `tests/character/test_acceptance_creation_chat.py` — start,
  one message, and the refusals, over `TestClient` only.

## Interfaces

- `POST /api/v1/character/runs/{runId}/creation` → 201, no body, `CsrfAuth`. 401 `NOT_AUTHENTICATED`,
  403 `CSRF_TOKEN_INVALID`, 404 `NOT_FOUND` (foreign/unknown run, unavailable content), 409
  `CHARACTER_EXISTS`.
- `POST /api/v1/character/creation/{conversationId}/messages` `{"text": "…"}` (min length 1) → 200. 401,
  403, 404 (unknown or foreign conversation, membership lost), 422 `VALIDATION_ERROR`.
- Both answer `CreationReply`: `conversationId`, `reply`, `sheet`, `step`, `stepNumber` (1–7),
  `canSave`, `saved`, `error`. Start's `reply` is `service.render_greeting(...)` — deterministic, no
  model call.
- `sheet` (`SheetSoFar`, all nullable): `name`, `race`, `characterClass`, `level`, `alignment`,
  `abilities` (six scores or null), `maxHp`, `armourClass`, `speed`, `skills` (list, empty until built),
  `equipment` (item names, empty until built), `appearance`, `backstory`.
- `step` enum, in order: `raceClass`, `scores`, `identity`, `skills`, `alignment`, `equipment`,
  `review`.
- `tests/character/conftest.py::scripted_model` (WI1 delivers, qa consumes): a fixture returning
  `install(*turns)`, called after `client` and before the first request; it monkeypatches
  `app.modules.character.service.chat_model`. Each turn is one model step — a `str` is the Keeper's
  words, a `(tool_name, args)` tuple is one tool call whose real tool runs before the next turn is
  consumed, an `Exception` instance is raised from the model call.

## Open questions

None product-visible.
