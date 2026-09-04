# Phase 3 — UI Specification: Consultation (customer chat)

Produced by the ui-ux-designer; binding for every Phase-3 frontend step (the
consultation UI formerly outlined as step 4.1, moved into this phase). Read
[`../phase-1/shared-knowledge.md`](../phase-1/shared-knowledge.md) and
[`../phase-2/shared-knowledge.md`](../phase-2/shared-knowledge.md) "Frontend
conventions" + "Landed decisions" first — file placement, hook/stub rules,
`queryKeys.ts`, and the SSE client contract all carry over unchanged.

Shared conventions for every spec below (Phase-1/2 conventions continue to
apply; deltas are marked):

- MUI v6/v7, Material Design 2 look, stock components only; palette tokens
  only, never hardcoded colors. Icons are Material Symbols via
  `<Icon>glyph_name</Icon>` — **never** `@mui/icons-material`.
- All strings via react-i18next `t()` — full key list in §11, including
  `aria-label`s. **Deliberate exemptions** (server-generated display content,
  rendered verbatim, same rule as Phase 2): message bodies, chat titles,
  source titles, tool-result values/labels coming from the backend
  (assumption texts, rule notes, preference summaries), recommendation
  rationale lines, and operation failure messages.
- Markdown: `react-markdown` + `remark-gfm`, raw HTML off (never add
  `rehype-raw`), links rendered as external MUI `Link`s — exactly the Phase-2
  §7 configuration. **Assistant messages only**; user messages render as
  plain text (§6).
- Data via TanStack Query over the typed `openapi-fetch` client. **The
  Phase-2 "no optimistic updates" rule gets exactly one exemption**: the
  user's own outgoing chat message (§3.2). Nothing else is optimistic.
- Forms: the composer is a plain controlled input. No RHF/Zod anywhere in
  this phase.
- Dates/times via `Intl` (`toLocaleString(i18n.language, …)`), pattern
  pinned in §6.
- **No token streaming, ever.** The chat rhythm is
  `seen → typing… → completed message` per `docs/general/architecture.md` — do not
  build any partial-message rendering.
- No new dependencies. The typing-dots animation is `sx` keyframes, not a
  library.
- **Backend field names are not yet frozen.** Where this spec touches message
  parts it lists **Data needs** (illustrative names from the step-3.4
  outline). The coordinating PM reconciles final JSON:API attribute names
  with the architect before the wiring step; renderers must be written
  against the stub types in §12 so only the hook layer changes at wiring
  time.

---

## 1. Route & file map

Routes (React Router v7, package `react-router`; extends the pinned table):

```tsx
<Route element={<AppLayout />}>
  <Route path="login" element={<LoginRoute />} />
  <Route path="register" element={<RegisterRoute />} />
  <Route element={<RequireAuth />}>
    <Route index element={<Navigate to="/consultations" replace />} />
    <Route path="consultations">
      <Route index element={<ConsultationsRoute />} />
      <Route path=":chatId" element={<ConsultationChatRoute />} />
    </Route>
    <Route element={<RequireAdmin />}>
      {/* /admin subtree unchanged */}
    </Route>
  </Route>
</Route>
```

**Decision — post-login home:** `/consultations` becomes the authenticated
home. The index route is a plain `<Navigate to="/consultations" replace />`
so there is exactly one canonical URL for the list; the Phase-1 login flow
(`navigate(from ?? "/")`) keeps working unmodified. **`HomeRoute.tsx` and
`HomeRoute.test.tsx` are deleted** (explicit placeholder). `HealthStatus` /
`useHealth` lose their only consumer and are **deleted too** (Phase-0 done
criterion, long since superseded); remove the `home.*` i18n block, keep
`app.*`.

| Concern | In the URL | Not in the URL |
|---|---|---|
| Which chat | `/consultations/:chatId` path param | — |
| Composer draft text | — | local `useState` |
| Sources expanded / assumptions expanded | — | local `useState` per message block |
| Optimistic outgoing message | — | mutation/cache state (§3.2) |

Nothing else belongs in the URL: the list has no filters in this phase.

**Files** (landed convention: route components in `frontend/src/routes/`,
shared components **flat** in `frontend/src/components/`, hooks in
`frontend/src/hooks/`; the step-4.1 outline's `toolResults/` subdirectory is
overruled — flat with a `ToolResult` prefix):

| File | Content |
|---|---|
| `frontend/src/routes/ConsultationsRoute.tsx` | §4 list. |
| `frontend/src/routes/ConsultationChatRoute.tsx` | §5 chat view shell + state machine. |
| `frontend/src/components/MessageBubble.tsx` | §6. |
| `frontend/src/components/MessageSources.tsx` | §7. |
| `frontend/src/components/TypingIndicator.tsx` | §2.2. |
| `frontend/src/components/LiveConnectionAlert.tsx` | §2.3 — extraction of the Phase-2 disconnect Alert (now used by two layouts). |
| `frontend/src/components/ToolResultBlock.tsx` | §8.1 frame + dispatcher + generic fallback (§8.6) + subtle rows (§8.7). |
| `frontend/src/components/ToolResultCatalogueSearch.tsx` | §8.2. |
| `frontend/src/components/ToolResultSpecComparison.tsx` | §8.3. |
| `frontend/src/components/ToolResultLicenceFitCheck.tsx` | §8.4. |
| `frontend/src/components/ToolResultCostEstimator.tsx` | §8.5. |
| `frontend/src/components/RecommendationCard.tsx` | §9. |
| `frontend/src/hooks/useChats.ts` | `useChats()`, `useChat(chatId)`, `useCreateChat()`, `useDeleteChat()` + types `Chat`. |
| `frontend/src/hooks/useChatMessages.ts` | `useChatMessages(chatId)`, `useSendMessage(chatId)` + types `ChatMessage`, `MessageSource`, `ToolCall`, `Recommendation`. |
| `frontend/src/hooks/useServerEvents.ts` | Existing; §3.1 adds binding requirements. |

All presentational components (`MessageBubble`, `MessageSources`,
`TypingIndicator`, every `ToolResult*`, `RecommendationCard`) receive
**already-fetched data as props and translate their own chrome strings**;
they never call hooks from `useChats`/`useChatMessages` themselves — this is
what lets §12's stubbed fixtures exercise them fully.

**Query keys** — extend `frontend/src/queryKeys.ts` with builders (never
hand-typed arrays):

| Key | Query |
|---|---|
| `["chats", "list"]` | `GET /api/chats` (owner-scoped server-side; hook walks pages via `meta.totalCount`, sorted by last activity desc) |
| `["chats", "detail", chatId]` | `GET /api/chats/{id}` (carries `activeOperationId`) |
| `["chatMessages", chatId]` | `GET /api/chat-messages?filter[chat]=…` (hook walks **all** pages, delivers oldest → newest) |

**The chat UI never reads `/api/operations`** — that endpoint is
`current_admin` and stays that way (shared-knowledge §R2). All turn state
derives from `chat.activeOperationId` (§3.3).

Mutations: `useCreateChat` invalidates `["chats"]`; `useDeleteChat`
invalidates `["chats"]` (a 404 counts as success — the row is gone either
way); `useSendMessage` invalidates `["chatMessages", chatId]` and
`["chats"]` (last-activity and `activeOperationId` both move) on success.

---

## 2. Shared building blocks

### 2.1 Reused as-is

`EmptyState` (Phase-2 §2.2) for every empty/error surface below.
`OperationProgress` is **not** reused in chat — the typing indicator (§2.2)
is the chat-appropriate progress surface; never show a percent bar in the
timeline.

### 2.2 `TypingIndicator`

An assistant-styled bubble (same container styling as an assistant
`MessageBubble`, §6) containing three dots:

```tsx
<Box role="status" aria-label={t("consultations.chat.typing")}
     sx={{ display: "flex", gap: 0.75, px: 1, py: 0.5 }}>
  {[0, 1, 2].map((i) => (
    <Box key={i} sx={{
      width: 8, height: 8, borderRadius: "50%", bgcolor: "text.secondary",
      animation: "typingPulse 1.2s ease-in-out infinite",
      animationDelay: `${i * 0.2}s`,
      "@keyframes typingPulse": { "0%, 60%, 100%": { opacity: 0.3 }, "30%": { opacity: 1 } },
    }} />
  ))}
</Box>
```

No text inside the bubble; the `aria-label` carries the meaning. This is a
graded progress indicator — it must be visibly animated.

### 2.3 `LiveConnectionAlert`

Extraction of the Phase-2 disconnect surface so chat and admin share one
implementation. Encapsulates: `useServerEventsStatus()`, the **5-second
grace timer**, and
`<Alert severity="warning" icon={<Icon>sync_problem</Icon>} sx={{ mb: 2 }}>`
with `common.live.disconnected`. Renders `null` while connected or within
the grace window. **`AdminLayout` is refactored to use it** (identical
behavior); the `admin.live.disconnected` key moves to
`common.live.disconnected` (delete the `admin.live` block). In the chat view
it renders **between the timeline and the composer** (§5) — a user waiting
for a reply must see why nothing arrives.

---

## 3. SSE & the conversation state machine

No polling, no streaming. The sole live mechanism is SSE notification →
TanStack Query invalidation → refetch, plus the reconnect blanket refetch.

### 3.1 Requirements on `useServerEvents` (binding)

- New event mappings: `chat.message.created` → invalidate
  `["chatMessages"]` **and** `["chats"]` (list order + `activeOperationId`
  both change); `operation.updated` keeps invalidating `["operations"]`
  (admin screens) and **additionally invalidates `["chats"]` when the
  payload's `entityType === "chat"`** (the `activeOperationId` lifecycle
  lives on the chat resource — the customer never reads operations).
- **On reconnect**: extend the existing blanket invalidation with
  `["chats"]` and `["chatMessages"]` — a reply that landed during the gap
  must appear on reconnect without a reload.

### 3.2 Sending a message (`useSendMessage`)

`POST` of the user message (endpoint per generated client;
`filter[chat]`-scoped `chat-messages` create per step 3.4). The **only**
optimistic update in the app:

1. `onMutate`: append `{ localId, role: "user", body, state: "sending" }` to
   the `["chatMessages", chatId]` cache; clear the composer immediately;
   auto-scroll (§5).
2. On success: mark the optimistic entry `state: "sent"` (**this is
   "seen"** — the successful POST is the seen signal; there is no dedicated
   SSE event), then invalidate per §1. The refetch replaces the optimistic
   entry with the server row (match on `localId` echo if available,
   otherwise drop optimistic entries whenever a refetch delivers a newer
   user message — pin the mechanism at wiring time).
3. On error (network/4xx/5xx): mark the entry `state: "failed"`; do **not**
   remove it (§6 failed-send affordance); composer re-enabled with the text
   **not** restored (the bubble holds it; retry re-POSTs the same body).

Client-side validation: whitespace-only messages never send (send button
disabled). Over-length input shows `error` + helperText
`consultations.chat.messageTooLong` on the composer and disables send
(server max length is **4000 chars** — pinned in shared-knowledge; mirror it
as a frontend constant `MESSAGE_MAX_LENGTH`).

### 3.3 Turn states (binding rendering rules)

Derived state, computed in `ConsultationChatRoute` from two queries
(messages, chat detail) — never from `/api/operations` (admin-only):

| # | Condition (first match wins) | Timeline shows after the last message |
|---|---|---|
| 1 | Optimistic message `sending` | The user bubble with caption `CircularProgress size={12}` + `consultations.chat.sending`. |
| 2 | Optimistic message `failed` | The user bubble in failed styling with retry/discard (§6). |
| 3 | `chat.activeOperationId !== null` — **or** a send just succeeded and no newer assistant message has arrived yet — and the turn is **not stale** (row 4) | `TypingIndicator` bubble. The newest **user** message above it carries the caption `<Icon fontSize="inherit">check</Icon>` + `consultations.chat.seen` (no caption when no user message exists yet — the greeting turn is just the typing bubble). |
| 4 | Row-3 condition holds but the turn is **stale**: the newest user message's `createdAt` — or the chat's `createdAt` when no user message exists yet (the greeting turn) — is older than `CHAT_TURN_STALE_SECONDS` (150 s — a frontend constant mirroring the backend healing threshold pinned in shared-knowledge; re-evaluated by a component mounted only while row 3 holds, the Phase-2 `LiveDisconnectAlert` timer pattern — never a reset-state effect) | No typing bubble; a centered caption row `color="error"`: `<Icon fontSize="inherit">error</Icon>` + `consultations.chat.turnFailed`. Composer enabled — the next send triggers the server's stale-pointer healing and starts a fresh turn. |
| 5 | Otherwise (idle) | Nothing. The normal failure path — backend persists an apologetic assistant message and clears `activeOperationId` in the same transaction — renders as an **ordinary assistant bubble** (the apology is the error surface) with no extra chrome. |

**Resume-after-reload:** the same derivation runs on mount — a reloaded page
whose chat still has `activeOperationId` set immediately shows the typing
indicator with the "Seen" caption on the last user message; when
`chat.message.created` fires, the refetch lands the assistant message and
state falls through to idle. No special resume code path.

**Composer gating:** while state 1 or 3 holds, the send button is disabled
and Enter does nothing; the TextField itself stays **editable** (drafting
while the advisor types is fine). States 2/4/5 leave the composer fully
enabled.

---

## 4. ConsultationsRoute — `/consultations`

**Layout:**

```
┌ Header row ─────────────────────────────────────────────┐
│ Consultations (h4)                [ + NEW CONSULTATION ] │
└──────────────────────────────────────────────────────────┘
┌ Paper variant="outlined" ────────────────────────────────┐
│ Commuter bike for the city            Aug 26, 2026 14:02 │
│ First big bike                        Aug 20, 2026 09:15 │
│ New consultation          ● replying… Aug 27, 2026 08:30 │
└──────────────────────────────────────────────────────────┘
```

- Header: `<Stack direction="row" sx={{ mb: 2, alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 2 }}>`
  with `<Typography variant="h4" component="h1">`
  `consultations.list.title` and
  `<Button variant="contained" startIcon={<Icon>add_comment</Icon>}>`
  `consultations.list.newConsultation`.
- List: `<Paper variant="outlined">` wrapping
  `<List aria-label={t("consultations.list.listLabel")} disablePadding>`;
  one `<ListItemButton component={RouterLink} to={`/consultations/${id}`} divider>`
  per chat (server order: last activity desc), containing `<ListItemText>`:
  - `primary`: chat title verbatim, or `consultations.list.untitled` when
    the title is null/empty. Single line, `noWrap`.
  - `secondary`: last-activity timestamp via
    `toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" })`.
  - `secondaryAction` slot (`<Stack direction="row" spacing={1}
    alignItems="center">`): when the chat has an active operation
    (`activeOperationId` set) a `<Typography variant="caption"
    color="primary">` `consultations.list.replying` (color plus text —
    never color alone), and always a delete
    `<IconButton edge="end" aria-label={t("consultations.list.delete")}>`
    `<Icon>delete</Icon>` (see **Deleting** below).
- **Starting a consultation is always a deliberate action** — the primary
  button (`consultations.list.newConsultation`, "Ask the advisor"); a chat
  is never created on page load. `useCreateChat` → `POST /api/chats`
  (empty body) → on success `navigate(`/consultations/${id}`)`; the
  response carries `activeOperationId` set, so the chat view opens directly
  in the typing state and **the advisor's greeting + opening question
  arrives as the first message**. Pending: button disabled +
  `CircularProgress size={20}` startIcon (standard pattern). Error:
  `<Snackbar autoHideDuration={6000}>` with `<Alert severity="error">`
  `consultations.list.createError` — justified because nothing else on the
  page changes on failure.
- **Deleting (soft delete):** the row's delete IconButton opens the
  existing `ConfirmDialog` (2.13 component, already-translated strings:
  `consultations.list.deleteConfirmTitle` / `deleteConfirmBody` with the
  chat title or the untitled fallback interpolated, confirmLabel
  `consultations.list.deleteConfirm`, `confirmColor="error"`) →
  `useDeleteChat` → `DELETE /api/chats/{id}` → row disappears
  (invalidation). Mutation error renders in the dialog via its `hasError`
  slot. No undo affordance — the server keeps the row (soft delete), but
  restore is not a UI feature this phase.

**Data needs (list item):** chat id, title (nullable), last-activity
timestamp (`updatedAt`), `activeOperationId` (nullable). There is **no**
chat status column (shared-knowledge pins the schema) — the list renders no
status chip.

**States:**

| State | Rendering |
|---|---|
| Loading (`isLoading`, no cached data) | Header renders (button enabled — creation doesn't need the list); Paper with 4 placeholder `ListItem`s, each `<Skeleton variant="text" width="60%" />` + secondary `<Skeleton variant="text" width="30%" />`. |
| Background refetch | Keep current rows; nothing flashes (SSE refetches invisible). |
| Error | Header + `EmptyState` in place of the list: icon `error`, `consultations.list.loadError` title, `common.errors.serverError` body, action `<Button onClick={refetch}>` `common.retry`. |
| Empty (first-time user) | `EmptyState`: icon `forum`, `consultations.list.emptyTitle` / `emptyBody`, action = the New-consultation button (same mutation). The header button also stays. |
| Live update | A reply landing in any chat reorders/refreshes the list via SSE invalidation — no reload. |

---

## 5. ConsultationChatRoute — `/consultations/:chatId`

**Layout** (inside `AppLayout`'s `lg` Container; the chat column narrows for
readability):

```
Consultations / Commuter bike for the city      ← Breadcrumbs
┌ Box maxWidth 840, mx auto ───────────────────────────────┐
│                       ┌─────────────────────────────────┐│
│                       │ I ride to work daily…    (user) ││
│                       └────────────────────── Seen ✓ ───┘│
│ ┌───────────────────────────────────────┐                │
│ │ [🔍 Catalogue search result block]    │                │
│ │ Markdown answer …                     │                │
│ │ [Recommended for you: cards]          │                │
│ │ ▸ Sources (3)                         │   (assistant)  │
│ └───────────────────────────────────────┘                │
│ ┌ ● ● ● ┐                                 (typing)       │
│ └───────┘                                                │
│ [ LiveConnectionAlert when disconnected ]                │
│ ┌ sticky composer ────────────────────────────────────┐  │
│ │ [ Tell the advisor…  (multiline)          ] [send ▶]│  │
│ └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

- `<Breadcrumbs sx={{ mb: 2 }}>`:
  `<Link component={RouterLink} to="/consultations">`
  `consultations.chat.back` + `<Typography color="text.primary" noWrap>`
  chat title (or `consultations.list.untitled`).
- Column: `<Box sx={{ maxWidth: 840, mx: "auto" }}>`.
- **Timeline:** `<Stack spacing={2} role="log" aria-label={t("consultations.chat.timelineLabel")}>`
  of `MessageBubble`s oldest → newest, newest at the bottom. **The document
  scrolls** — no nested scroll container (this keeps mobile browsers and
  keyboard-avoidance sane).
- **Composer** (sticky):
  `<Box component="form" onSubmit={send} sx={{ position: "sticky", bottom: 0, py: 1.5, bgcolor: "background.default" }}>`
  wrapping `<Paper variant="outlined" sx={{ p: 1, display: "flex", alignItems: "flex-end", gap: 1 }}>`:
  - `<TextField multiline maxRows={6} fullWidth size="small" variant="outlined"
    placeholder={t("consultations.chat.composerPlaceholder")}
    aria-label={t("consultations.chat.composerLabel")} autoFocus />` (no
    visible label — the placeholder + aria-label carry it; a floating label
    on a chat composer is noise).
  - `<IconButton type="submit" color="primary" aria-label={t("consultations.chat.send")} disabled={…}>`
    `<Icon>send</Icon>`; while a send mutation is pending, the icon is
    replaced by `CircularProgress size={24}`.
  - **Enter sends; Shift+Enter inserts a newline** (`onKeyDown`: plain Enter
    with `!event.shiftKey && !event.nativeEvent.isComposing` →
    `preventDefault()` + submit). On touch devices the send button is the
    primary affordance; Enter behavior is unchanged (no user-agent
    sniffing).
  - Disabled rules per §3.3; whitespace-only always disabled.

**Auto-scroll** (bottom anchor `<div ref={bottomRef} />` after the
timeline):

- On first data render: instant `scrollIntoView({ behavior: "instant" })`.
- After the user's own send (optimistic append): smooth scroll, always.
- When an assistant message or the typing indicator appears: smooth scroll
  **only if** the viewport was within ~120 px of the bottom before the
  update; otherwise leave the scroll position alone (the user is reading
  history). No "jump to latest" button in this phase.

**Page-level states** (checked in order; breadcrumbs render once the chat is
loaded):

| State | Rendering |
|---|---|
| Chat or messages loading (no cached data) | Centered `CircularProgress size={48}` in a `role="status"` Box, `aria-label` `common.loading` — exact Phase-1 guard markup. No composer yet. |
| Error — 404 / not owner (backend returns 404 for both) | `EmptyState`: icon `search_off`, `consultations.chat.notFoundTitle` / `notFoundBody`, action `<Button component={RouterLink} to="/consultations">` `consultations.chat.back`. |
| Error — network/5xx | `EmptyState`: icon `error`, `consultations.chat.loadError` title, `common.errors.serverError` body, retry action (`refetch`). |
| Fresh chat (zero messages, `activeOperationId` set — the normal just-created case) | The timeline holds only the `TypingIndicator` (§3.3 row 3, no Seen caption): the advisor's greeting + opening question is on its way. Composer rendered, send disabled per §3.3. |
| Empty **idle** chat (zero messages, no active operation — rare: greeting turn stale/failed without apology) | In place of the timeline, a lightweight intro (not `EmptyState` — the composer is the action): `<Stack spacing={1} alignItems="center" sx={{ py: 6, textAlign: "center", color: "text.secondary" }}>` with `<Icon sx={{ fontSize: 56 }}>two_wheeler</Icon>`, `<Typography variant="h6" color="text.primary">` `consultations.chat.introTitle`, `<Typography variant="body2" sx={{ maxWidth: 440 }}>` `consultations.chat.introBody`. Composer autofocused — the user opening the conversation manually is the recovery path. |
| Conversation states | §3.3 table. |

---

## 6. `MessageBubble`

Props: the message (role, body, parts, timestamp, optimistic state) +
`onRetry?`/`onDiscard?` for failed sends. One component, two stylings:

| | User | Assistant |
|---|---|---|
| Alignment | `alignSelf: "flex-end"` | `alignSelf: "flex-start"` |
| Container | `<Paper elevation={0} sx={{ bgcolor: "primary.main", color: "primary.contrastText", px: 2, py: 1.25, borderRadius: 3 }}>` | `<Paper variant="outlined" sx={{ px: 2, py: 1.25, borderRadius: 3 }}>` |
| Max width | `maxWidth: { xs: "85%", sm: 560 }` | `maxWidth: { xs: "95%", sm: 720 }` (tool tables need room) |
| Body | Plain text, `<Typography variant="body1" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>` — user input is **never** rendered as Markdown | Markdown via the pinned react-markdown config (GFM, raw HTML off, external links) |

**Assistant message part order** (top → bottom inside the bubble):

1. Tool-call blocks (§8) — what the advisor did,
2. the Markdown body — the answer,
3. recommendation cards (§9) — the payoff,
4. sources toggle (§7) — the receipts.

**Timestamp:** `<Typography variant="caption" color="text.secondary">`
under every bubble (outside the Paper, aligned with the bubble edge). Same
calendar day as "now": `toLocaleTimeString(i18n.language, { timeStyle: "short" })`;
otherwise `toLocaleString(i18n.language, { dateStyle: "medium", timeStyle: "short" })`.

**Send-state captions** (user bubbles only, replaces the timestamp while
active): `sending` → spinner + `consultations.chat.sending`; `sent` on the
newest user message while a turn is in flight → check icon +
`consultations.chat.seen` (§3.3); `failed` → the Paper gets
`sx={{ bgcolor: "transparent", border: 1, borderColor: "error.main", color: "text.primary" }}`
and the caption row becomes `color="error"`:
`consultations.chat.sendFailed` + two `<Button size="small">`s —
`consultations.chat.sendRetry` (re-fires the mutation with the same body)
and `consultations.chat.sendDiscard` (removes the optimistic entry).

**Data needs (message):** id, role, created-at timestamp, markdown body,
plus the assistant parts consumed by §7–§9.

---

## 7. `MessageSources` (grading-critical)

Rendered when an assistant message carries ≥ 1 source. **Default:
collapsed** — but the toggle is always visible with a count, so provenance
is discoverable at a glance without burying the conversation.

- `<Divider sx={{ my: 1 }} />` above.
- Toggle: `<Button size="small" color="inherit"
  startIcon={<Icon sx={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 150ms" }}>expand_more</Icon>}
  aria-expanded={expanded}>` —
  `t("consultations.chat.sourcesToggle", { count })` ("Sources (3)").
- `<Collapse in={expanded}>` wrapping
  `<List dense disablePadding aria-label={t("consultations.chat.sourcesLabel")}>`;
  one `ListItem` per source with `<ListItemText>`:
  - `primary`: `<Link href={sourceUrl} target="_blank" rel="noopener noreferrer" variant="body2">`
    with the `sourceTitle` verbatim + a trailing
    `<Icon fontSize="inherit">open_in_new</Icon>` — every source is an
    external link (retrieved-content links never navigate the SPA).
  - `secondary`: `new URL(sourceUrl).hostname`, and when `headingPath` is
    present, ` · ` + the path segments joined with ` › `.

Local `useState` per message; expanded state is not persisted or in the URL.
Duplicate sources (same URL + headingPath) are de-duplicated by the renderer.

**Data needs (per source):** `sourceTitle`, `sourceUrl`, optional
`headingPath` (string list or pre-joined — either works).

---

## 8. Tool-call result renderers (grading-critical)

### 8.1 `ToolResultBlock` — frame & dispatcher

Every tool call on an assistant message renders as a **visually distinct,
always-expanded block** so graders see tool usage without interaction.
Frame:

```tsx
<Paper variant="outlined" sx={{ bgcolor: "action.hover", p: 1.5, mb: 1 }}>
  <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
    <Icon fontSize="small" sx={{ color: "text.secondary" }}>{glyph}</Icon>
    <Typography variant="overline" color="text.secondary">{label}</Typography>
    {/* §8.5 adds an "Estimate" chip here */}
  </Stack>
  {/* renderer body */}
</Paper>
```

Dispatch on tool name:

| Tool name | Renderer | Glyph | Label key |
|---|---|---|---|
| `catalogue_search` | §8.2 | `search` | `consultations.tools.catalogueSearch.title` |
| `spec_comparison` | §8.3 | `compare_arrows` | `consultations.tools.specComparison.title` |
| `licence_fit_check` | §8.4 | `fact_check` | `consultations.tools.licenceFitCheck.title` |
| `cost_estimator` | §8.5 | `payments` | `consultations.tools.costEstimator.title` |
| `record_preference` | §8.7 subtle row | `bookmark_added` | — |
| `flag_unknown_bike` | §8.7 subtle row | `flag` | — |
| anything else | §8.6 generic | `build` | raw tool name verbatim (forward compatibility — no `t()`) |

A tool result the renderer cannot parse (shape mismatch) falls back to §8.6
rather than crashing — wrap dispatch in a shape check, not a try/catch
around render.

**Data needs (per tool call):** tool name (string), structured
JSON-serializable result. The input/args summary is **not** rendered in this
phase (the surrounding prose describes intent).

### 8.2 Catalogue search

`<List dense disablePadding>`; one `ListItem` per result (cap display at 8;
if more, a trailing caption `consultations.tools.catalogueSearch.more` with
`{{count}}` remaining):

- `primary`: model display name (body2).
- `secondary`: up to three compact spec fragments joined with ` · ` (e.g.
  category, power `{{value}} kW`, weight `{{value}} kg` — render only
  present values, units via `consultations.specUnits.*`).

Zero results: `<Typography variant="body2" color="text.secondary">`
`consultations.tools.catalogueSearch.noResults`. Names are plain text — no
links (detail pages are Phase 4, §9 rule applies).

**Data needs (per result):** motorbike id, display name, a small set of key
verified spec values (category, power kW, weight kg — nullable).

### 8.3 Spec comparison (the in-chat comparison — product decision)

`<TableContainer sx={{ overflowX: "auto" }}>` **inside the block** wrapping
`<Table size="small" sx={{ minWidth: 120 * (bikes + 1) }}
aria-label={t("consultations.tools.specComparison.tableLabel")}>`:

- Header row: first cell `consultations.tools.specComparison.attribute`,
  then one cell per bike (name, `whiteSpace: "nowrap"`).
- One body row per attribute: label cell (attribute display label + unit),
  then per-bike value cells. **Null/unknown renders an em dash `—`** with
  `aria-label` `common.unknown` — never blank, never a guess.

**Narrow-viewport behavior (binding):** the table never wraps or drops
columns — it scrolls horizontally *within the bubble* (`overflowX: "auto"`
on the container; the bubble's `maxWidth` from §6 bounds it). This is the
pinned answer to the step-4.1 layout risk.

**Data needs:** ordered bike list (id + name), ordered attribute rows
(label — server-provided or a pinned attribute key the client can map to
`consultations.specFields.*`, unit, per-bike nullable values). Whether
labels arrive translated-server-side or as keys is a PM/architect
reconciliation point.

### 8.4 Licence / fit check

`<Stack spacing={1}>`; one row per rule:
`<Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>`:

- `<Chip size="small" label={t(`consultations.tools.licenceFitCheck.verdict.${verdict}`)} color={pass: "success", fail: "error", unknown: "default"} />`
  — color **plus** translated label.
- `<Box>`: `<Typography variant="body2">` rule label; below it
  `<Typography variant="caption" color="text.secondary">` the numbers used,
  verbatim from the result (e.g. "35.0 kW / 189 kg = 0.185 kW/kg") — the
  visible evidence is a grading point. `unknown` verdicts show the
  server-provided reason (e.g. "seat height not verified") verbatim.

**Data needs (per rule):** rule id/label, verdict `pass|fail|unknown`, a
human-readable evidence/values string (or structured numbers the client can
join — verbatim string preferred, flag for reconciliation).

### 8.5 Cost estimator

Header frame (§8.1) additionally carries
`<Chip size="small" variant="outlined" color="warning" label={t("consultations.tools.costEstimator.estimate")} />`
— the "this is an estimate" disclosure is **always visible**, not behind a
toggle.

Body:

1. `<Table size="small">`: one row per line item — label cell (verbatim) +
   right-aligned amount cell formatted via
   `new Intl.NumberFormat(i18n.language, { style: "currency", currency, maximumFractionDigits: 0 })`
   (currency code from the result; **data need** — assumed EUR, §14). Final
   row: `consultations.tools.costEstimator.total` +
   amount, both `<strong>` (`sx={{ fontWeight: "bold" }}` on the cells).
   A per-period qualifier (e.g. "/year") arrives as part of the
   server-provided line-item label — verbatim.
2. Assumptions disclosure: same toggle pattern as §7 —
   `<Button size="small" color="inherit" startIcon={rotating expand_more}>`
   `t("consultations.tools.costEstimator.assumptions", { count })` +
   `<Collapse>` wrapping a `<List dense>` of assumption strings verbatim.
   Default collapsed; the visible count + the Estimate chip are the
   always-on disclosure.

**Data needs:** line items (label, numeric amount), total, currency code,
assumptions (list of strings — the step-3.3 result schema's `assumptions`
field).

### 8.6 Generic fallback

Two-column `<Table size="small">` of the result object's top-level entries:
key verbatim / `JSON.stringify`-ed value (objects pretty-printed in
`<Typography variant="caption" component="pre" sx={{ m: 0, whiteSpace: "pre-wrap" }}>`).
Header label = raw tool name. Guarantees **every** tool call is visible even
when the frontend predates the tool.

### 8.7 Subtle rows — `record_preference` & `flag_unknown_bike`

**Decision: visible but subtle.** These are bookkeeping writes, not
information retrieval — a full Paper block per captured preference would
drown the interview (it fires many times per conversation). But tool
visibility is graded and preference capture is a product feature, so they
render as one-line caption rows (in the §6 part order, position 1, mixed
in call order with full blocks):

```tsx
<Stack direction="row" spacing={0.75} sx={{ alignItems: "center", color: "text.secondary", mb: 0.5 }}>
  <Icon fontSize="inherit">{glyph}</Icon>
  <Typography variant="caption">{text}</Typography>
</Stack>
```

- `record_preference`:
  `t("consultations.tools.preferenceNoted", { attribute, value, firmness })`
  where `firmness` interpolates the translated
  `consultations.tools.firmness.hard|soft|exploring` ("must-have" /
  "nice-to-have" / "exploring"). Attribute and value verbatim from the
  result. **Data needs:** attribute, value, firmness enum.
- `flag_unknown_bike`:
  `t("consultations.tools.unknownBikeFlagged", { name })` — name verbatim.
  **Data needs:** the flagged bike name.

---

## 9. `RecommendationCard`

Rendered when an assistant message carries recommendations: a heading
`<Typography variant="subtitle2" sx={{ mt: 1 }}>`
`consultations.recommendations.heading`, then
`<Stack direction={{ xs: "column", sm: "row" }} spacing={2} useFlexGap sx={{ flexWrap: "wrap", my: 1 }}>`
of cards, each `<Card variant="outlined" sx={{ width: { xs: "100%", sm: 280 } }}>`:

1. Image: `<CardMedia component="img" height={140} image={cardUrl}
   srcSet={`${thumbUrl} 320w, ${cardUrl} 640w`} sizes="280px"
   alt={name} loading="lazy" sx={{ objectFit: "cover" }} />` — the Phase-2
   variant URLs (`thumb` 320 / `card` 640; `detail` 1280 unused here). **No
   image** (models may publish without one): a 140px
   `<Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "action.hover" }}>`
   with `<Icon sx={{ fontSize: 48, color: "text.secondary" }}>two_wheeler</Icon>`.
2. `<CardContent>`:
   - `<Typography variant="subtitle1" component="h3">` — model name.
   - Key specs: up to four `<Typography variant="caption" color="text.secondary" display="block">`
     lines, `{t(`consultations.specFields.${field}`)}: {value} {unit}` —
     render only non-null values, order: category, power kW, wet weight kg,
     seat height mm.
   - `<Typography variant="body2" sx={{ mt: 1 }}>` — the one-line rationale
     verbatim.

**Decision — link target (explicit):** the catalogue model detail page does
**not exist** until Phase 4. In this phase the card is **non-interactive**:
no `CardActionArea`, no disabled button, no dead link (Phase-1 precedent:
dead controls are noise). **The href contract is reserved now**:
`/catalogue/:motorbikeId` — Phase 4 wraps the card content in
`<CardActionArea component={RouterLink} to={`/catalogue/${motorbikeId}`}>`
and changes nothing else. `RecommendationCard` therefore takes
`motorbikeId` as a prop already, even though Phase 3 doesn't use it.

**Data needs (per recommendation):** motorbikeId, display name, image
variant URLs (thumb + card, nullable), rationale line, key verified spec
values (category, power kW, wet weight kg, seat height mm — nullable).

---

## 10. App shell integration

- **Nav:** in `AppLayout`, the Home button becomes
  `<Button color="inherit" component={RouterLink} to="/consultations">`
  `nav.consultations` (replace `nav.home` usage; delete the key). Admin
  button unchanged. Still no drawer — two destinations.
- **AppBar title** keeps linking to `/` (which redirects to
  `/consultations`).
- **SSE:** the single `EventSource` stays mounted in `AppLayout`
  (`ServerEventsConnection`) — no per-route connections. §3.1's new
  mappings land in `useServerEvents`.
- **Disconnect warning:** `LiveConnectionAlert` (§2.3) renders in the chat
  view above the composer and (refactored) in `AdminLayout`. The
  consultation **list** does not render it — the list degrades gracefully
  (stale ordering) and the alert would be noise on the home screen.
- **Mobile:** the list is already phone-friendly; the chat column is fluid
  (`maxWidth: 840` only bounds desktop), bubbles cap at 85–95% width,
  comparison tables scroll horizontally inside bubbles (§8.3), the sticky
  composer sits above the on-screen keyboard because the document itself
  scrolls (no nested scroll trap).

---

## 11. i18n keys (merge into `frontend/src/locales/en/translation.json`)

`nav.home` and the `home.*` block are **deleted** (§1); `admin.live` moves
to `common.live` (§2.3). Everything else below is new.

```json
{
  "nav": {
    "consultations": "Consultations"
  },
  "common": {
    "live": {
      "disconnected": "Live updates interrupted — reconnecting…"
    }
  },
  "consultations": {
    "list": {
      "title": "Consultations",
      "listLabel": "Your consultations",
      "newConsultation": "Ask the advisor",
      "untitled": "New consultation",
      "replying": "Advisor is replying…",
      "loadError": "Could not load your consultations",
      "emptyTitle": "Ask the advisor",
      "emptyBody": "The advisor interviews you about your experience, licence, budget and how you ride — then recommends motorcycles from our verified catalogue.",
      "createError": "Could not start a consultation. Please try again.",
      "delete": "Delete consultation",
      "deleteConfirmTitle": "Delete this consultation?",
      "deleteConfirmBody": "“{{title}}” and its conversation will be removed from your list.",
      "deleteConfirm": "Delete"
    },
    "chat": {
      "back": "Consultations",
      "timelineLabel": "Conversation",
      "notFoundTitle": "Consultation not found",
      "notFoundBody": "This consultation does not exist or was removed.",
      "loadError": "Could not load this consultation",
      "introTitle": "Tell the advisor about yourself",
      "introBody": "Start with anything — your riding experience, what you want a bike for, or a model you're curious about. The advisor will guide the conversation from there.",
      "composerLabel": "Message",
      "composerPlaceholder": "Tell the advisor…",
      "send": "Send",
      "messageTooLong": "This message is too long.",
      "sending": "Sending…",
      "seen": "Seen",
      "sendFailed": "Not sent.",
      "sendRetry": "Send again",
      "sendDiscard": "Discard",
      "typing": "The advisor is typing…",
      "turnFailed": "The advisor could not finish this reply — please send your message again.",
      "sourcesToggle": "Sources ({{count}})",
      "sourcesLabel": "Sources"
    },
    "tools": {
      "catalogueSearch": {
        "title": "Catalogue search",
        "noResults": "No matching models.",
        "more": "+ {{count}} more"
      },
      "specComparison": {
        "title": "Spec comparison",
        "tableLabel": "Spec comparison",
        "attribute": "Spec"
      },
      "licenceFitCheck": {
        "title": "Licence & fit check",
        "verdict": {
          "pass": "Pass",
          "fail": "Fail",
          "unknown": "Unknown"
        }
      },
      "costEstimator": {
        "title": "Cost estimate",
        "estimate": "Estimate",
        "total": "Total",
        "assumptions": "Assumptions ({{count}})"
      },
      "preferenceNoted": "Preference noted — {{attribute}}: {{value}} ({{firmness}})",
      "firmness": {
        "hard": "must-have",
        "soft": "nice-to-have",
        "exploring": "exploring"
      },
      "unknownBikeFlagged": "“{{name}}” isn't in our catalogue yet — noted for research."
    },
    "recommendations": {
      "heading": "Recommended for you"
    },
    "specFields": {
      "category": "Category",
      "powerKw": "Power",
      "wetWeightKg": "Wet weight",
      "seatHeightMm": "Seat height"
    },
    "specUnits": {
      "kw": "kW",
      "kg": "kg",
      "mm": "mm"
    }
  }
}
```

(`common.loading`, `common.retry`, `common.unknown`,
`common.errors.serverError` already exist and are reused.)

---

## 12. Stub fixtures (UI-only steps)

Phase-1/2 stub pattern: real `useQuery`/`useMutation` results over fixture
data, inside the hook files (`useChats.ts`, `useChatMessages.ts`), header
comment naming the wiring step that deletes them wholesale. Components
written against the stubs must survive replacement unchanged. **The fixture
set below is binding — it must exercise every state in this spec:**

Chat list (5 chats, stable fake-ULID ids):

1. **`chat-interview`** — titled, recent last-activity, no active operation.
   The rich conversation below.
2. **`chat-typing`** — titled, `activeOperationId` set, newest user message
   timestamped "just now" → list shows "Advisor is replying…", opening it
   shows the typing indicator with a "Seen" caption on the last user
   message (resume-after-reload state).
3. **`chat-stale`** — titled, `activeOperationId` set, newest user message
   timestamped **older than `CHAT_TURN_STALE_SECONDS`** → the §3.3 state-4
   error row (composer enabled).
4. **`chat-new`** — null title, zero messages, `activeOperationId` set,
   fresh `createdAt` → the fresh-chat greeting state (typing bubble, no
   Seen caption). The `useCreateChat` stub navigates here, and the stub
   appends the advisor's greeting after ~1.5 s (pointer clears) —
   exercises the advisor-speaks-first arrival.
5. **`chat-empty`** — null title, zero messages, no active operation, old
   `createdAt` → untitled fallback + the rare idle intro state.

The `useDeleteChat` stub removes the chat from the fixture table
(exercises the §4 confirm dialog end-to-end).

`chat-interview` messages (oldest → newest):

1. Assistant greeting (short markdown, no tools/sources — the
   advisor-speaks-first opener with its opening interview question).
2. User message (plain text with a line break — proves `pre-wrap`).
3. Assistant message: markdown body containing a heading, a list **and a
   GFM table** (proves the react-markdown config); one `record_preference`
   subtle row; no sources.
4. User message.
5. Assistant "kitchen-sink" message carrying **all four** tool results —
   catalogue search (3 results, one with null specs), spec comparison
   (3 bikes × ≥ 6 attributes with several nulls → em dashes + horizontal
   scroll on phone), licence/fit check (one `pass`, one `fail`, one
   `unknown`, each with evidence strings), cost estimator (4 line items,
   total, 3 assumptions, currency EUR) — plus one `flag_unknown_bike`
   subtle row, one **unknown tool** (`some_future_tool`, exercises §8.6),
   **3 sources** (one with `headingPath`, one duplicate URL to prove
   de-dup), and **2 recommendations** (one with image variant URLs, one
   with `null` image → fallback box).

`useSendMessage` stub: appends optimistically, resolves after ~800 ms
(exercises `sending` → `seen`), and a magic input (message text
`"fail"`) rejects — exercises the failed-send bubble with retry/discard.

Timestamps: mix same-day and older-day values (proves the two `Intl`
formats).

---

## 13. Accessibility / UX checklist (applies to §2–§10)

- **Progress semantics:** the typing indicator is `role="status"` with a
  translated `aria-label`; send-pending spinners live in the caption/button,
  never a page overlay; page-level loading uses the Phase-1 `role="status"`
  spinner. These are graded surfaces.
- **Timeline semantics:** the message stack is `role="log"` (implicit polite
  live region) with a translated `aria-label`; new assistant messages are
  announced without stealing focus. Focus stays in the composer after send.
- **Color is never the only signal:** verdict chips carry translated labels;
  the failed bubble pairs the error border with "Not sent." text; the seen
  state pairs the check icon with the word "Seen".
- **Keyboard:** Enter sends / Shift+Enter newline, IME-safe
  (`isComposing` guard); the send control is a real `type="submit"` button;
  toggles (`sources`, `assumptions`) are real `Button`s with
  `aria-expanded`.
- **Links:** every source link and any markdown link:
  `target="_blank" rel="noopener noreferrer"`; retrieved/LLM content stays
  inert (raw HTML off, no `dangerouslySetInnerHTML`); in-app navigation is
  `RouterLink` (list items are `ListItemButton component={RouterLink}` —
  real hrefs, middle-click works).
- **Images:** `loading="lazy"`, `alt` = model name; the no-image fallback
  keeps card height stable.
- **Tables:** translated `aria-label`s on comparison tables; null values
  render an em dash with `aria-label` `common.unknown`, never an empty cell.
- **Long content:** `overflowWrap: "anywhere"` on user text (pasted URLs
  must not break layout); bubble `maxWidth`s bound everything else.
- **No dead controls:** recommendation cards are non-interactive until
  Phase 4 (§9) — no disabled buttons, no placeholder links.

---

## 14. Resolutions (reconciled with the architect by the PM, 2026-08-27)

The questions this spec originally raised are resolved as follows;
[`shared-knowledge.md`](shared-knowledge.md) is the binding source for all
of them:

1. **Message-part field names — pinned in shared-knowledge §"Persisted
   JSONB shapes":** `sources[]` items carry `sourceTitle`, `sourceUrl`,
   `headingPath` (pre-joined string or null), `score`; `toolCalls[]` items
   carry `tool`, `arguments`, `result`, `status`, `error`;
   `recommendations[]` items carry `motorbikeId`, `name`, `imageUrl`
   (card-variant path or null — derive thumb from it by replacing the
   variant suffix), `rationale`, `matchedPreferences`, `keySpecs`.
   Comparison rows are keyed by the **frozen camelCase spec field names**;
   the client maps them via `consultations.specFields.*` (extend that block
   to all frozen fields in step 3.10) and renders an unmapped key verbatim.
   Licence-check rules arrive as `{rule, label, verdict, evidence}` where
   `label`/`evidence` are server-composed English strings rendered verbatim
   (same i18n exemption as operation messages). Cost estimator: `currency`
   is always `"EUR"` (project-wide unit pin).
2. **Chat titles:** server sets the title once from the first user message
   (truncated to 160; the greeting never sets it); not user-editable. As
   specced.
3. **Deleting consultations (owner decision 2026-08-27):** soft delete —
   `DELETE /api/chats/{id}` sets `deleted_at`; list affordance + confirm
   dialog per §4. No restore UI.
4. **Chat status:** there is no status column (schema pinned in
   shared-knowledge; `deleted_at` is the only lifecycle flag); no chip,
   nothing to decide.
5. **Who speaks first (owner decision 2026-08-27):** the **advisor** —
   creating a chat (always via the explicit "Ask the advisor" button, never
   on page load) enqueues a greeting turn: greeting + opening interview
   question, like a seller in a real store. §5's fresh-chat state renders
   the incoming greeting; the intro hint survives only as the rare
   idle-empty fallback.
6. **Message max length:** 4000 chars, pinned; mirrored as
   `MESSAGE_MAX_LENGTH` (§3.2).
7. **Concurrent turns:** the backend rejects a POST on a chat with a
   genuinely active turn with **409 `response-pending`** and self-heals
   stale pointers (terminal or timed-out operations) by accepting the
   message; the UI guard (§3.3) is UX only. A 409 in the wild maps to a
   quiet refetch of the chat detail, no error surface.
