# Chat and consultation

The customer-facing consultation: tables, turn lifecycle, wire shapes, UI.
The reasoning inside a turn is [`retrieval-advisor.md`](retrieval-advisor.md).

## Tables

**`chats`** — `user_id` FK, `title String(160)` nullable,
`active_operation_id String(26)` nullable (**no FK**), `deleted_at`,
timestamps.

- `title` is set once from the first *user* message and truncated; the greeting
  never sets it, and it is not editable.
- `active_operation_id` is the turn pointer: non-NULL means "the advisor is
  replying". It is the only thing the typing indicator derives from.
- **Soft delete.** Every read filters `deleted_at IS NULL`; there is no restore
  API. A second delete returns 404.
- `updated_at` is bumped explicitly on every append, so it *is* last activity.
- Deliberately **no status column**.

**`chat_messages`** — `chat_id` FK, `role` (`user`/`assistant`), `body Text`,
and three JSONB arrays defaulting to `[]`: `tool_calls`, `sources`,
`recommendations`. Immutable: no `updated_at`. Order `created_at ASC, id ASC`.
The system prompt is code and tool traffic is JSONB, so neither is ever a row.

**`chat_preferences`** — `chat_id` FK, `attribute String(64)`,
`value String(256)`, `firmness` (`hard`/`soft`/`exploring`),
`superseded_by_id` self-FK.

- Recording the same attribute again inserts a new row and stamps the old one's
  `superseded_by_id` in one transaction. Active = `superseded_by_id IS NULL`.
- The attribute is normalised (lower-case, whitespace/`_`/`-` runs collapsed to
  a single space, truncated); the value is stored as phrased.
- Re-recording an unchanged preference yields a third row. By design — the
  history is the record of the interview.
- Firmness: `hard` = a constraint not to violate, `soft` = a leaning,
  `exploring` = trying it on. Suggested attributes: experience, licence, use
  case, budget, height, inside leg, style, brand, luggage, pillion.

## Persisted JSONB shapes

Stored **camelCase** and validated on read, so every key is always present.

```text
toolCalls[]       {id, tool, arguments{}, result{}, status: succeeded|failed, error|null}
sources[]         {chunkId, motorbikeId, sourceDocumentId, sourceUrl|null,
                   sourceTitle, headingPath|null, score}
recommendations[] {motorbikeId, name, imageUrl|null, rationale, matchedPreferences[],
                   keySpecs{category, engineCc, powerKw, wetWeightKg, seatHeightMm, priceBand}}
```

- **Every executed call is persisted**, including the write tools; a failed call
  has `result: {}` plus `error`.
- `sources` are deduped by `sourceDocumentId` keeping the best score, ordered
  `-score, chunkId`, capped at 8.
- `recommendations` are deduped by `motorbikeId`, first wins, and are a
  **write-time snapshot** — the card keeps rendering after the catalogue moves
  on. Staleness is accepted.
- Recorded results are **unfenced**; only the copy handed to the model is fenced.

## Endpoints

Both resources are `current_user` + CSRF on writes. An unknown, foreign or
soft-deleted chat is **404 `not-found`**.

| Endpoint | Notes |
|---|---|
| `GET /api/chats` | own, non-deleted, sorted **`-updatedAt`**, paginated |
| `GET /api/chats/{id}` | |
| `POST /api/chats` | strict empty envelope → 201; **also starts the greeting turn**, so the response already carries `activeOperationId` |
| `DELETE /api/chats/{id}` | soft delete, 204, no SSE event |
| `GET /api/chat-messages?filter[chat]=` | filter **required** (absent → 400 `missing-filter`), sorted `createdAt ASC, id ASC` |
| `POST /api/chat-messages` | attributes `{chatId, body}` → 201, or **409 `response-pending`** |

There is no PATCH on either resource. `chatId` is an *attribute*, not a
relationship — the internal JSON:API layer has no relationship machinery.

## Turn lifecycle

`POST /api/chat-messages` runs in a pinned order:

```text
owned-chat-or-404 → heal_stale_turn (409 if it refuses) → append_user_message → start_response → 201
```

Healing runs **before** the append, so a 409 leaves nothing behind.

`start_response` creates the operation (`type="chat.response"`,
`entity_type="chat"`), sets the pointer, touches the chat, commits, then
enqueues `chat.respond(chat_id, operation_id)` — ids only.

`append_assistant_message` clears `active_operation_id` in the same transaction
on both the success and the apology path, then emits `chat.message.created`.

**Stale-turn healing** (`heal_stale_turn`): if the pointed-at operation is
terminal or gone, clear the pointer and accept. If it is `queued`/`running` and
older than `stale_turn_seconds()` = `AGENT_TIMEOUT_SECONDS + 30`, fail it with
"Response timed out.", clear, accept. Otherwise refuse → 409. The frontend
mirrors this as `CHAT_TURN_STALE_SECONDS = 150`; **keep the two in lockstep.**

**Failure policy** in the job: the four transient gateway error types become
`TransientJobError`, so the broker retries and the operation stays `running`.
Anything else persists a fixed apology message ("I am sorry — something went
wrong … Please send your message again."), fails the operation and is *not*
re-raised. The apology path takes ids and reloads the rows, because ORM
instances are expired after the rollback. A chat deleted mid-turn fails the
operation and writes nothing.

## SSE

One event is emitted by `append_assistant_message`:

```json
{"event":"chat.message.created","chatId":"…","messageId":"…","role":"assistant"}
```

User messages emit nothing — the POST response is the acknowledgement.
`operation.updated` arrives from the generic lifecycle with
`entityType:"chat"`.

The client invalidates `["chatMessages"]` + `["chats"]` on the message event and
`["chats"]` on a chat-scoped operation event. `/api/operations` is admin-only,
so the customer UI derives turn state **only** from `chat.activeOperationId`.
"Seen" means the POST succeeded. No streaming, no polling.

## Frontend

Routes `/consultations` and `/consultations/:chatId`; the index route redirects
to `/consultations`.

Hooks: `useChats` (`useChats`, `useChat`, `useCreateChat`, `useDeleteChat` —
a 404 on delete counts as success) and `useChatMessages` (`useChatMessages`,
`useSendMessage`).

**The one optimistic update in the app** is the outgoing message. Reconciliation
happens in the `queryFn`: fetched pages are merged with cached `sending`/
`failed` rows and everything else is dropped. A 409 takes the failed-bubble
path and invalidates `["chats"]`; no snackbar.

Turn states:

| State | Surface |
|---|---|
| sending | spinner caption, composer disabled |
| failed | error styling + retry / discard |
| replying (`activeOperationId` set, not stale) | typing bubble; newest user message captioned "Seen ✓"; composer disabled |
| stale (> 150 s) | error caption row, composer re-enabled |
| idle | composer ready |

`MessageBubble` renders an assistant message in a pinned order: **tool blocks →
Markdown body → recommendation cards → sources toggle.** User text is plain
`pre-wrap`, never Markdown.

Components: `TypingIndicator` (`role="status"`), `LiveConnectionAlert` (5 s
grace before claiming live updates are down), `MessageSources` (collapsed by
default with a count, deduped by `sourceUrl|headingPath`, external links),
`RecommendationCard` (whole surface links to `/catalogue/{motorbikeId}`; the
thumbnail is derived from the card variant by suffix swap), `ToolResultBlock`
plus per-tool renderers for `catalogue_search`, `spec_comparison`,
`licence_fit_check` and `cost_estimator`; `record_preference` and
`flag_unknown_bike` render as one-line notes, and anything else — including
`retrieve_bike_knowledge` and `present_recommendations` — falls back to a
generic key/value table with the raw tool name.

Composer: Enter sends, Shift+Enter newlines, IME-safe, `MESSAGE_MAX_LENGTH =
4000`. A chat is created only by the explicit "Ask the advisor" button, never on
page load.

## Demo script

`backend/scripts/demo_conversation.py` drives eight turns over plain HTTP with a
throwaway account and asserts: the advisor greets first · ≥ 3 distinct tools
used · ≥ 1 recommendation pointing at approved ids · sources present wherever
snippets were retrieved · exactly one backlog row created for the uncatalogued
bike · a second login re-reads an identical timeline. It cleans up after itself.

```bash
docker compose exec app-web python scripts/demo_conversation.py
```

## Known issues

- **Concurrent-turn race** — two simultaneous POSTs both return 201. See
  [`../general/decisions.md`](../general/decisions.md#open-decisions).
- An `alembic downgrade` can block on an open `/api/events` session; terminate
  idle-in-transaction connections first.
