---
phase: 3
step: "3.6"
title: Wire chat live (S1)
summary: Regenerate API types, replace both stub hook files with real openapi-fetch hooks, and wire the SSE-driven conversation state machine — seen, typing via activeOperationId, resume-after-reload, stale-turn fallback.
effort: 3
dependencies: ["3.4", "3.3", "3.5"]
---

# Step 3.6 — Wire chat live (S1)

**Effort: 3** — the components don't change; the two stub files die
wholesale and the SSE invalidation map grows two entries. **Starts only
after 3.3 + 3.5 are merged.**

Binding contracts: `docs/roadmap/phase-3/ui-spec.md` (§1, §3) and
`docs/roadmap/phase-3/shared-knowledge.md` (§SSE / events, §Frontend
conventions — delta). Agent: **frontend-dev**.

## Outline

- First action: regenerate types (2.15 landed sequence:
  `docker compose run --rm -T app-cli app openapi export >
  frontend/openapi.json` → `node-cli pnpm exec openapi-typescript …`).
- Delete both stub hook files wholesale; real hooks unwrap envelopes in-hook
  (2.15 pattern: `Chat = {id} & ChatAttributes`, `ChatMessage = {id} &
  ChatMessageAttributes`), page-walk on both lists, `ChatError` with
  `status` + `code` (built like `ProductError`); `useDeleteChat` → real
  `DELETE /api/chats/{id}`, invalidating `["chats"]` (a 404 counts as
  success — the row is gone either way). `useSendMessage` keeps the
  §3.2 optimistic contract (the only optimistic update in the app); a 409
  `response-pending` maps to a quiet refetch of the chat detail.
- `useServerEvents.ts` invalidation map: `chat.message.created` →
  invalidate `["chatMessages"]` + `["chats"]`; `operation.updated` with
  `entityType === "chat"` → additionally invalidate `["chats"]` (keep the
  existing `["operations"]` invalidation); reconnect blanket gains
  `["chats"]` + `["chatMessages"]`.
- Typing state = `chat.activeOperationId !== null` (never `/api/operations`
  — it is admin-only); stale fallback per ui-spec §3.3 row 4 (mounted-timer
  pattern, `CHAT_TURN_STALE_SECONDS`).
- Tests: rework the 3.4 route tests onto `stubFetch` JSON:API fixtures (the
  2.15 precedent — component sources unchanged), SSE event → invalidation
  unit tests, optimistic append/replace/failed paths.

## Verification

- In the browser: "Ask the advisor" → typing bubble → the advisor's
  greeting + opening question arrives → send → seen ✓ → animated typing
  bubble over SSE → assistant markdown reply; reload mid-response shows
  typing again and completes; delete a consultation from the list (confirm
  dialog, row disappears, deep link 404s); a second account's browser sees
  nothing of it; `make frontend-test` + lint + typecheck green. **This
  closes milestone M2.**

## Risks / notes

- If any generated attribute name differs from shared-knowledge, stop and
  report — the contract is frozen at 3.3; do not adapt silently.
- No polling fallback of any kind; native EventSource retry only (Phase-2
  pinned rule).
