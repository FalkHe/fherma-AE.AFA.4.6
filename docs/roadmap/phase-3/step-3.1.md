---
phase: 3
step: "3.1"
title: Chat persistence
summary: The chats/chat_messages/chat_preferences tables in one migration (incl. soft delete via deleted_at), plus ChatService with message append, title-once, soft delete, preference supersession, and the chat.message.created announcement seam.
effort: 4
dependencies: ["1.1", "2.1", "2.6"]
---

# Step 3.1 — Chat persistence

**Effort: 4** — three tables, one migration, and a service with a handful of
functions; the supersession logic and the announce-after-commit ordering are
the only subtleties. **The only Phase-3 migration.**

Binding contract: `docs/roadmap/phase-3/shared-knowledge.md` (§DB schema,
§Persisted JSONB shapes, §SSE / events). Agent: **backend-dev**.

## Outline

- `backend/app/db/models/chat.py`: `Chat`, `ChatMessage`, `ChatPreference`
  exactly as pinned in shared-knowledge (ULID PKs, TIMESTAMPTZ, native enums
  `chat_message_role('user','assistant')` /
  `preference_firmness('hard','soft','exploring')` with `values_callable`,
  JSONB `tool_calls`/`sources`/`recommendations` defaulting `'[]'`, no
  relationships). One Alembic migration off the Phase-2b head
  `485b2042d7f8` (`add_manufacturers_table`, landed 2026-08-27); downgrade
  drops both enum types explicitly (copy `4ea01933a43b`).
- `backend/app/services/chat_service.py` (module-level functions,
  `AsyncSession` first, services commit): `create_chat(session, user_id)`,
  `get_owned_chat(session, chat_id, user_id)` (None for wrong owner **or**
  soft-deleted — routes map to 404), `list_chats(session, user_id, *,
  limit, offset) -> (rows, total)` ordered `updated_at DESC, id DESC`
  filtering `deleted_at IS NULL`, `soft_delete_chat(session, chat)` (sets
  `deleted_at`, commits, no event),
  `append_user_message(session, chat, body)` (sets `title` from the first
  user message truncated to 160 — only when still null; bumps
  `updated_at`; commits), `append_assistant_message(session, chat, body, *,
  tool_calls=(), sources=(), recommendations=())` (clears
  `active_operation_id` in the same transaction, commits, then announces
  `chat.message.created` via `operation_service.notify` — the pinned
  emitter), `list_messages(session, chat_id)` ordered
  `created_at ASC, id ASC`.
- Preference functions: `record_preference(session, chat_id, *, attribute,
  value, firmness)` — same chat + same attribute ⇒ insert new row and set
  the old row's `superseded_by_id` in one transaction;
  `active_preferences(session, chat_id)` filters
  `superseded_by_id IS NULL`.
- Tests (`FakeAsyncSession` pattern from `backend/tests/services/`):
  supersession (old row marked, new row active), title set once and only
  once (and **never** by an assistant message), message ordering, soft
  delete excludes from list/get, announce-after-commit ordering observable
  via the conftest notification interpreter.

## Verification

- `make backend-test` green; `alembic upgrade head` / `downgrade -1`
  round-trips; `alembic check` clean (schema fully expressed in the ORM).

## Risks / notes

- Zero deviations from the pinned schema — 3.3's serialization and the
  frontend stubs are being built against it in parallel.
- `active_operation_id` is a plain string, no FK — do not "improve" it.
