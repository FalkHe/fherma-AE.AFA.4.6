---
phase: 4
step: "4.5"
title: Concurrent-turn 409 race fix (Q4)
summary: Serialize POST /api/chat-messages per chat with a migration-free SELECT … FOR UPDATE on the chat row, so two truly concurrent sends answer exactly one 201 and one 409 — closing Phase-3 open question Q4.
effort: 2
dependencies: ["3.17"]
---

# Step 4.5 — Concurrent-turn 409 race fix (Q4)

**Effort: 2** — one locking read in one route path plus a race-proving
harness. **Gated on owner confirmation** — see
[`open-questions.md`](open-questions.md) OQ1; if the owner prefers to defer,
this step is dropped without touching any other Phase-4 step.

Binding contracts: `docs/roadmap/phase-4/shared-knowledge.md` (*Q4 fix
contract*) and the Phase-3 pins it protects
(`docs/roadmap/phase-3/shared-knowledge.md` — *Chat response job &
stale-turn healing*, Landed decisions 3.5). Background:
`docs/roadmap/phase-3/open-questions.md` Q4. Agent: **backend-dev**. Zero
deviations — a deviation is a stop-and-report.

## Outline

- `chat_service` gains a locking read (e.g. `lock_owned_chat(session,
  chat_id, user_id)` or `get_owned_chat(..., for_update=True)`) issuing
  `SELECT … FOR UPDATE` on the chat row — used **only** in the
  `POST /api/chat-messages` path, before `heal_stale_turn`.
- Behaviour under race: the second concurrent POST blocks on the row lock,
  then sees the fresh `active_operation_id` → 409 `response-pending`. The
  healing matrix itself (3.5's `heal_stale_turn`) is unchanged.
- No wire change, no migration, no new error code; `GET` paths and
  `POST /api/chats` untouched.
- Files touched: `backend/app/services/chat_service.py`,
  `backend/app/api/endpoints/chat_messages.py`, their tests — disjoint from
  4.3/4.4, so this may run in a parallel backend session.

## Verification

- Suite + lint green (compiled-SQL assertion that the statement carries
  `FOR UPDATE`, per the 3.7 `RecordingSession` convention if the fake
  session can't express it).
- Live race proof (stack up, worker up): two truly parallel
  `POST /api/chat-messages` for the same chat (shell `&`-fork with curl, or
  a small asyncio harness) → exactly one 201 + one 409, repeated a few
  runs; exactly one operation row created.
- On success, remove Q4 from `docs/roadmap/phase-3/open-questions.md` and
  record the outcome under this phase's `## Landed decisions`.

## Risks / notes

- Do not widen the lock to other chat reads — the SSE/idle-transaction
  lock pitfall from 3.1's Landed decisions is real; the lock must live and
  die inside the single POST transaction.
- The apologetic-message / worker paths never take this lock (the worker
  loads via `get_chat`, not the owned read).
