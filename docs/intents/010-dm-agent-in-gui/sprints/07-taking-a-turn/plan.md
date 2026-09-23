---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 07

The screen is driven by the transcript: a notice tick only says "something is new" and the client
re-reads. A running turn is recognised from the transcript itself (an open turn whose last entry is not
narration), because nothing on the wire says so.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | The composer: open with a text field and Send; closed with the in-voice line for a running turn, a pending question or a pending roll | sends trimmed text on Enter or Send and clears; ignores empty; closed states show their line and nothing clickable | – |
| 2 | frontend | The thinking line with its spinner, announced to assistive tech | renders the first wording in a live region | – |
| 3 | frontend | The transcript shows the thinking line at its foot, inside the scroller, while a turn runs | line present when asked for, absent otherwise, after the rows | I2 |
| 4 | frontend | The notice stream: subscribe per run, tick per update, reopen after a fatal close, close on unmount or run change | tick on an update message, silence on keepalive, reopen when closed, cleanup | – |
| 5 | frontend | The transcript read tells whether a turn is unfinished | pure rule on the recorded entries; hook returns the flag | – |
| 6 | frontend | Sending words: the player's row at once, the turn call, composer state from the read, and live refresh on every tick and when the call settles; module README updated | send shows the row at once and closes the composer; tick re-reads; composer reopens when the turn ends with nothing pending; reload during a turn shows the thinking line | WI1–5 |

Strict file ownership, one owner per file; only WI6 edits the module README.

## Interfaces
- I1 `Composer({ state, onSend }): ReactElement`, `state: "open" | "turnRunning" | "awaitingChoice" | "awaitingRoll"`, `onSend(text: string): void` (trimmed, never empty, only when `state === "open"`). Strings: `composer.placeholder`, `composer.send`, `composer.turnRunning`, `composer.awaitingChoice`, `composer.awaitingRoll` in `play.json` (exist already).
- I2 `ThinkingLine(): ReactElement` — spinner + `thinking.first`, `aria-live` region.
- I3 `Transcript({ rows, thinking }: { rows: TranscriptRow[]; thinking?: boolean })`.
- I4 `useRunNotices(runId: string, onTick: () => void): void` — `EventSource` on `${VITE_API_URL ?? ""}/api/v1/playthrough/campaign/{runId}/stream` with `withCredentials: true`; `onTick` per `data: {"type":"updated",...}` message; keepalives and reconnects silent; on `error` with `readyState === CLOSED` reopen; close on unmount / `runId` change.
- I5 `isTurnUnfinished(events: EventRead[]): boolean` (pure: non-empty and last event `type !== "narration"`) exported from `transcript.ts`; `usePlayTranscript` gains `turnUnfinished: boolean`.
- I6 `useTakeTurn({ runId, rows }) → { send(text: string): void; isSending: boolean; pending: { text: string; at: string } | null }` — `POST /api/v1/game/runs/{runId}/turn` body `{text}`; `pending` cleared once `rows` holds a `player` row whose id was not in the snapshot taken at send. In `PlayRoute`: `turnRunning = isSending || (awaiting === "none" && turnUnfinished)`; composer state `awaitingRoll` / `awaitingChoice` when `awaiting` starts with `roll:` / `answer:`, else `turnRunning` or `open`; `onTick` and mutation settle both `invalidateQueries({ queryKey: ["transcript", runId], cancelRefetch: false })`.

## Acceptance tests (qa)
No end-to-end runner is configured and this sprint adds none. Component tests cover the criteria:
AC1 → WI1, WI6 · AC2 → WI3, WI4, WI6 · AC3 → WI5, WI6 · AC4 → WI5, WI6 · AC5 → WI4.
The sprint lead checks the running screen in a browser before shipping.

## Order
WI1–WI5 in parallel, WI6 after all five.
