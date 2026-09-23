---
author: architect
owner: agent
created: 2026-09-23
updated: 2026-09-23
---
# Research: sprint 010/07 — taking a turn

## Facts

**The notice stream exists, server-side only.** `GET /api/v1/playthrough/campaign/{run_id}/stream`
(`playthrough/routes.py:221-273`): membership checked before the response is returned, then a loop that
sleeps `sse_poll_interval_seconds` (2.0) and compares `service.latest_event_id`. A change yields
`data: {"type":"updated","id":"<eventId>"}` (`:264-265`), otherwise `: keepalive`. The generator returns
after `sse_max_lifetime_seconds` (300.0, `core/settings.py:23-24`) or on disconnect — so **the server
closes every stream after five minutes** (AC5's "after it closes"). The route is `CurrentAuth`, i.e.
cookie only, no CSRF header (`auth/dependencies.py:37`). **No frontend consumer exists**: the path appears
in `frontend/src/api/schema.d.ts:254` and nowhere else; nothing re-reads on a tick today.

**A tick carries no content.** The client must re-read `GET …/campaign/{run_id}/events`
(`routes.py:197-217`), which answers `{events, awaiting}` — the same read `usePlayTranscript` already makes.

**EventSource, not the shared client.** `openapi-fetch` cannot consume `text/event-stream`, and the test
dispatcher JSON-stringifies every body (`frontend/src/test/network.ts:135-139`), so a fetch-stream client
could not be tested without changing shared test infrastructure. `EventSource` restarts the connection by
itself when the server closes it (MDN, *Using server-sent events* — "if the connection between the client
and server closes, the connection is restarted"), which is AC5 for the 300 s cutoff; a *fatal* close
(HTTP error status, wrong content type) leaves `readyState === CLOSED` and is not retried, so the hook
reopens itself on `error` when `readyState === CLOSED`. It needs `{ withCredentials: true }` because
`VITE_API_URL` is cross-origin in dev (`.env.dist:12`); CORS already allows credentials from the frontend
origin (`backend/app/main.py:46-52`). The URL is built from `import.meta.env.VITE_API_URL ?? ""` — the
second and only other place in the app that names the network besides `core/api/client.ts:27-30`; it stays
inside this module (one caller, AGENTS.md's promote-on-second-caller rule).

**The turn call (sprint 03).** `POST /api/v1/game/runs/{run_id}/turn`, `CsrfAuth`, body `{text}` only
(`extra="forbid"`, `game/schemas.py:15-24`), answering `{turnId, kind, awaiting}` (`game/routes.py:30-47`).
It is synchronous: the request lives as long as the turn. The host's read timeout measured ≥280 s
(`docs/intents/010-dm-agent-in-gui/sprints/03-turn-endpoint/review.md:27`), above the two minutes D5
allows, and `fetch` imposes no timeout of its own — so no client-side abort is needed this sprint.
The client never renders the response body (brief assumption); it only ends the wait.

**The transcript read.** `usePlayTranscript(runId, heroName)` → `{rows, awaiting, isPending, isError,
retry}`, key `["transcript", runId]`, `limit: 500` (`hooks/usePlayTranscript.ts:42-57`). `staleTime` is
30 s (`core/queryClient.ts:11`), but `invalidateQueries` overrides `staleTime` and refetches active
queries — so a tick is exactly `queryClient.invalidateQueries({queryKey: ["transcript", runId]})`
(TanStack Query 5.102.8, context7 `/tanstack/query/v5.90.3`). Pass `cancelRefetch: false` so a burst of
ticks cannot keep cancelling the read in flight. No party-rail refresh this sprint — the rail is not built
(`routes/PlayRoute.tsx:22-25`).

**"In flight" after a reload.** Nothing on the wire says it. `awaiting` (`playthrough/service.py:2893-2940`)
distinguishes only a *pending* question or roll; a running turn and a finished one both answer `"none"`.
The checkpoint's "next step queued" flag that `run_turn` uses (`game/README.md` "Quirks") has no route.
The transcript does carry it, though: `record_action` writes `player_action` as the turn's first event
(`game/agent/nodes.py:241-251`) and `record_narration` writes `narration` as its last, immediately before
`END` (`nodes.py:350-359`, `agent/graph.py:43`); every other event comes from a tool, mid-turn. So
**`awaiting === "none"` plus a last event whose `type` is not `"narration"` means a turn is open and
unfinished** — computed from `EventRead.turnId`/`type`, both on the wire (`schema.d.ts:702-717`). Two
known false positives, both sprint 10's business (D5's give-up timer), neither reachable without a real
failure: a turn that crashed mid-flight, and a narration whose text came back empty (no event written,
`nodes.py:349`).

**The optimistic row.** Rows carry the event id (`transcript.ts:25-30`). Take a snapshot of the current
row ids at send; drop the optimistic row as soon as the transcript holds a `player` row whose id is not in
that snapshot — which the first tick after `record_action`'s commit delivers. Purely derived, no effect,
and a duplicate is impossible in either direction.

**Strings.** `composer.placeholder`, `composer.send`, `composer.turnRunning`, `composer.awaitingChoice`,
`composer.awaitingRoll`, `thinking.first` and `thinking.long` all exist in
`core/i18n/locales/en/play.json`. This sprint uses the first six; `thinking.long` and `failure.*` are
sprint 10. **No i18n file is edited** — one less shared file.

## Work items

Strict file ownership, because two agents staging the same file crossed twice last sprint: **each file
below has exactly one owner, and only WI6 touches `README.md`** (every other item returns its README
paragraph in its handoff, WI6 pastes them). WI1–WI5 are disjoint and run in parallel; WI6 runs last.

- **WI1 Composer** — new `components/Composer.tsx` (+ test). Open: text field, Send, submits on Enter,
  clears itself, trims, ignores empty (mirror `character/components/Composer.tsx`). Closed: the matching
  line, nothing clickable. No network, no buttons (sprint 09 owns those).
- **WI2 Thinking line** — new `components/ThinkingLine.tsx` (+ test): spinner plus `thinking.first`, and
  an `aria-live` region. One wording only.
- **WI3 Transcript foot** — `components/Transcript.tsx` + `Transcript.test.tsx` only: accept `thinking`
  and render WI2's line at the foot, inside the scroller, after the rows, so stay-at-latest still works.
- **WI4 Notice stream** — new `hooks/useRunNotices.ts` (+ test, with a fake `EventSource` via
  `vi.stubGlobal`): subscribe, reopen on a fatal close, close on unmount/`runId` change.
- **WI5 Transcript hook** — `transcript.ts`, `usePlayTranscript.ts` and their tests only: export
  `isTurnUnfinished(events)` and return `turnUnfinished` alongside today's fields.
- **WI6 Send and wiring** — new `hooks/useTakeTurn.ts`, `routes/PlayRoute.tsx`, `PlayRoute.test.tsx`,
  `README.md`: the mutation, the optimistic row, the derived composer state, and the tick → invalidate
  wiring. Depends on I1–I5 as written, not on the other items' code.

## Interfaces

- **I1** `Composer({ state, onSend }): ReactElement`, `state: "open" | "turnRunning" | "awaitingChoice" |
  "awaitingRoll"`, `onSend(text: string): void` (trimmed, never empty, only when `state === "open"`).
- **I2** `ThinkingLine(): ReactElement`.
- **I3** `Transcript({ rows, thinking }: { rows: TranscriptRow[]; thinking?: boolean })`.
- **I4** `useRunNotices(runId: string, onTick: () => void): void` — calls `onTick` per
  `{"type":"updated"}` message; keepalives and reconnects are silent.
- **I5** `isTurnUnfinished(events: EventRead[]): boolean` (pure: non-empty and last event `type !==
  "narration"`); `usePlayTranscript` gains `turnUnfinished: boolean`.
- **I6** `useTakeTurn({ runId, rows }) → { send(text: string): void; isSending: boolean; pending: { text:
  string; at: string } | null }` — `POST /api/v1/game/runs/{runId}/turn` with `{text}`, `pending` cleared
  by the snapshot rule above. In `PlayRoute`: `turnRunning = isSending || (awaiting === "none" &&
  turnUnfinished)`; composer state is `awaitingRoll`/`awaitingChoice` when `awaiting` starts with
  `roll:`/`answer:`, else `turnRunning` or `open`; `onTick` and the mutation settling both invalidate
  `["transcript", runId]`.

## Open questions

None product-visible. Assumptions, for veto: the composer stays closed with D12's own wording while a
question or roll is pending, since its buttons only arrive in sprint 09; a turn that breaks mid-flight
keeps the thinking line until sprint 10's give-up timer replaces it.
