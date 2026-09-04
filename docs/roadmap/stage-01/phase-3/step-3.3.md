---
phase: 3
step: "3.3"
title: Chat JSON:API endpoints & message-part contract
summary: The chats and chat-messages resources — session-cookie auth, CSRF, ownership-as-404, soft-delete DELETE, required chat filter, and the frozen message-part serialization (toolCalls/sources/recommendations, activeOperationId). Freezes the Phase-3 OpenAPI surface (S1).
effort: 4
dependencies: ["3.1", "2.3", "1.3"]
---

# Step 3.3 — Chat JSON:API endpoints & message-part contract

**Effort: 4** — two resources over the landed jsonapi.py layer plus the
OpenAPI-typed JSONB item schemas; the ownership and validation matrix is the
bulk of the tests. **Merging this step (with 3.5) opens sync point S1.**

Binding contract: `docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§JSON:API
resources, §Persisted JSONB shapes). Agent: **backend-dev**.

## Outline

- `backend/app/api/endpoints/chats.py`, `chat_messages.py`;
  `backend/app/api/schemas/chats.py`, `chat_messages.py` — reuse
  `app/api/jsonapi.py` verbatim (per-resource `Document`/`ListDocument`
  subclasses; hand-rolled `…CreateRequest` with `extra="forbid"` at every
  level).
- Resources exactly as pinned: `chats` (GET list `-updatedAt` sorted,
  `deleted_at IS NULL` / detail / POST empty-attributes / **DELETE →
  soft delete via `chat_service.soft_delete_chat`, 204**;
  `Depends(current_user)`, writes `Depends(csrf_protect)`); `chat-messages`
  (GET with **required**
  `filter[chat]` → 400 `missing-filter`, >1 member → 400 `invalid-filter`,
  sorted `createdAt ASC, id ASC`; POST with attributes `{chatId, body}` —
  `chatId` is an attribute, not a relationship).
- The three JSONB attributes (`toolCalls`, `sources`, `recommendations`)
  serialize verbatim and are typed in OpenAPI as arrays of the pinned item
  schemas (Pydantic models with camelCase aliases; `arguments`/`result` as
  open objects).
- Ownership = 404 `not-found` for wrong-owner, unknown **and soft-deleted**
  ids (no existence leak; applies to DELETE too — deleting twice → 404).
  Body validation: stripped non-empty, ≤ 4000 chars (schema constant).
- **No enqueue in this step** (2.3 precedent): POST persists the user
  message via `chat_service.append_user_message` only; `activeOperationId`
  stays null until 3.5 wires `start_response`.
- After any write `await session.refresh(row)` before rendering
  (`chats.updated_at` server `onupdate` — the landed `MissingGreenlet`
  rule).
- Tests: ownership 404s (both resources), soft-delete matrix (list
  excludes, GET/DELETE-again/messages-filter 404), missing/invalid filter
  400s, 422 body validation, CSRF 403, message ordering, JSONB
  pass-through.

## Verification

- Curl with a cookie jar: register → login → `POST /api/chats` →
  `POST /api/chat-messages` → `GET /api/chat-messages?filter[chat]=…` shows
  the message with empty part arrays; `DELETE /api/chats/{id}` → 204, the
  chat vanishes from the list and GETs 404; a second user gets 404 on the
  same chat; `app openapi export` includes both resources with typed part
  schemas.

## Risks / notes

- The OpenAPI surface frozen here is what 3.6 generates types against and
  what 3.13 fills — attribute names must match shared-knowledge exactly.
- Do not add relationships/includes machinery; `chatId` as attribute is the
  pinned simplification.
