---
phase: 3
step: "3.5"
title: Minimal chat responder job
summary: The Taskiq chat.respond job answering with the plain LLM (no tools yet) behind the start_response enqueue seam, wired into the message POST and — advisor-speaks-first — the chat POST, with operation lifecycle, stale-pointer healing, the apologetic-message failure path, and the new ADVISOR_MODEL config key.
effort: 3
dependencies: ["3.3", "2.5", "2.6", "2.16"]
---

# Step 3.5 — Minimal chat responder job

**Effort: 3** — one service seam, one job module, one route wiring; the
healing rule and failure path carry the subtlety. **Merging this step (with
3.3) opens sync point S1.**

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§Chat response
job & stale-turn healing, §SSE / events). Agent: **backend-dev**.

## Outline

- `backend/app/services/chat_response_service.py`:
  `generate(session, chat, operation)` — rebuild context from full persisted
  history (role + body only), render
  `backend/app/llm/prompts/advisor_system.md` (first minimal version:
  persona, motorcycle-advisory domain, refuse out-of-domain, **and: when
  the history is empty, greet the customer and ask the opening interview
  question** — like a seller in a real store), one
  `get_chat_model(settings.advisor_model).ainvoke`, persist via
  `chat_service.append_assistant_message` (which clears the pointer and
  announces). New config key **`ADVISOR_MODEL=openai/gpt-4.1-mini`**
  (`.env.dist` + `config.py`) — `CHAT_MODEL` stays the
  ingestion/extraction + utility model. **This function is the seam 3.13
  rewires — the job never changes again.**
- `chat_service.start_response(session, chat) -> Operation`: create
  operation (`type='chat.response'`, entity `chat`/`chat.id`), set
  `active_operation_id`, commit, then `enqueue_chat_response(...)` —
  in-function import of `app.jobs.chat` (the 2.14 `enqueue_ingestion`
  pattern); autouse stub fixture in `tests/conftest.py` records enqueues.
- Wire into the 3.3 message-POST route: validate → `append_user_message` →
  **stale healing** (pointer already terminal → clear + accept;
  `queued`/`running` older than `AGENT_TIMEOUT_SECONDS + 30` s → fail it
  with `"Response timed out."` + clear + accept; genuinely active → 409
  `response-pending`) → `start_response` → 201.
- **Advisor speaks first:** wire `start_response` into the chat-POST route
  too — creating a chat immediately enqueues the greeting turn; the 201
  carries `activeOperationId` set. The greeting must not set the title
  (title comes from the first user message; 3.1 guards this).
- `backend/app/jobs/chat.py`: task `chat.respond(chat_id, operation_id)` —
  ids only, own session, `operation_service` lifecycle
  (`start`/`succeed`/`fail`), `TransientJobError` for gateway timeouts only,
  any other exception → persist the apologetic assistant message +
  operation `failed` (never a silent dead chat). Append `app.jobs.chat` to
  `app-worker`'s command in `compose.yaml`.
- Tests: healing matrix (terminal / timed-out / active), enqueue recorded on
  POST, failure path persists the apology and clears the pointer
  (`tests/jobs/` `WorkerSession` pattern).

## Verification

- Stack + worker up: curl-POST a chat → a greeting assistant message
  arrives within seconds (title stays null); curl-POST a message →
  assistant reply row appears and `activeOperationId` returns to null;
  `curl -N /api/events` shows `operation.updated` (entityType `chat`) then
  `chat.message.created`; with `OPENROUTER_API_KEY` blanked in the worker,
  the apologetic message is persisted and the operation is `failed`.

## Risks / notes

- `AGENT_TIMEOUT_SECONDS` (120) enters config **here** only if needed by the
  healing constant — otherwise it lands in 3.13; keep the healing threshold
  reading `settings` so 3.13 doesn't touch this code. *(Pinned: add both
  agent config keys in 3.13; until then the healing threshold may reference
  a module constant set to 150 s total with a TODO naming 3.13.)*
- Do not add retrieval or tools here — the plain-LLM reply/greeting is
  deliberate (M2's demo); RAG enters once, in 3.13, as a tool.
- Never hardcode a model id — `ADVISOR_MODEL`/`CHAT_MODEL` are `.env`
  knobs and may change.
