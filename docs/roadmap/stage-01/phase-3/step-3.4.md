---
phase: 3
step: "3.4"
title: Chat shell, UI-only
summary: Consultation list and chat view routes with composer, markdown message bubbles, typing indicator, and the conversation state machine — all against stub hooks; deletes HomeRoute and rehomes the post-login landing to /consultations.
effort: 4
dependencies: ["3.2", "1.6", "2.4"]
---

# Step 3.4 — Chat shell, UI-only

**Effort: 4** — two routes, the bubble/typing components, the state-machine
derivation, and the pinned stub fixtures; zero backend code needed.

Binding contracts: `docs/roadmap/stage-01/phase-3/ui-spec.md` (§1–§6, §10–§13 —
layouts, states, i18n keys, fixtures) and
`docs/roadmap/stage-01/phase-3/shared-knowledge.md` (§Frontend conventions — delta).
Agent: **frontend-dev**.

## Outline

- Routes per ui-spec §1: `frontend/src/routes/ConsultationsRoute.tsx`
  (list, §4) and `frontend/src/routes/ConsultationChatRoute.tsx` (chat
  view + state machine, §5, §3.3); index route becomes
  `<Navigate to="/consultations" replace />`. **Delete `HomeRoute.tsx` +
  test, `HealthStatus`, `useHealth`, the `home.*` i18n block; `nav.home` →
  `nav.consultations`** (ui-spec §1/§10).
- Components: `MessageBubble.tsx` (ui-spec §6 — react-markdown + remark-gfm
  for assistant only, plain `pre-wrap` text for user, timestamps, send-state
  captions), `TypingIndicator.tsx` (§2.2), `LiveConnectionAlert.tsx`
  (§2.3 — extract from `AdminLayout`, refactor `AdminLayout` to use it,
  move `admin.live.disconnected` → `common.live.disconnected`).
- Composer per ui-spec §5: sticky, multiline, Enter-sends/Shift+Enter
  newline (IME-safe), disabled rules per §3.3, auto-scroll rules.
- Delete affordance per ui-spec §4: per-row delete `IconButton` +
  `ConfirmDialog` (the existing 2.13 component, already-translated
  strings); stubbed `useDeleteChat` removes the row from the fixture table.
- Stub hooks (Phase-1/2 stub pattern, header comment naming step 3.6 as the
  deleting step): `frontend/src/hooks/useChats.ts` (`useChats`,
  `useChat(chatId)`, `useCreateChat`, `useDeleteChat` + type `Chat`) and
  `frontend/src/hooks/useChatMessages.ts` (`useChatMessages`,
  `useSendMessage` + types `ChatMessage`, `MessageSource`, `ToolCall`,
  `Recommendation`, `ChatError`) over the **binding fixture set of ui-spec
  §12** (5 chats: interview — opening with the advisor's greeting — /
  typing / stale / new-with-incoming-greeting / idle-empty; the send stub
  with the magic `"fail"` input; the delete stub removing rows). The
  optimistic-send exemption (§3.2) is implemented here against the stub.
- `frontend/src/queryKeys.ts` gains `chats.list()`, `chats.detail(id)`,
  `chatMessages.byChat(chatId)` builders; i18n keys from ui-spec §11 merged
  into `frontend/src/locales/en/translation.json`.
- Constants: `MESSAGE_MAX_LENGTH = 4000`, `CHAT_TURN_STALE_SECONDS = 150`
  (shared-knowledge mirrors).
- Tests: state-machine table rows 1–5 via the fixtures, Enter/Shift+Enter,
  failed-send retry/discard, markdown GFM table render, both `Intl`
  timestamp formats.

## Verification

- `make frontend-test` + `pnpm lint` + `pnpm typecheck` green;
  `/consultations` renders the stub list (all four states reachable), the
  interview chat renders bubbles with a GFM table, the typing fixture shows
  the animated indicator + Seen caption, the stale fixture shows the
  failed-turn row.

## Risks / notes

- Components written against the stubs must survive 3.6's wholesale stub
  deletion unchanged — import types only from the two hook files.
- Do not build any part renderers here (tool blocks/sources/cards are 3.10);
  `MessageBubble` renders body + timestamp + send states only, with the part
  slots left as clearly marked extension points.
