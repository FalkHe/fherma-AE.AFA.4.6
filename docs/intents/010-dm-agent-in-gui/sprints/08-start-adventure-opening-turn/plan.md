---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 08

Entering an adventure and the opening turn are two calls: the run screen enters, then hands the play
screen a one-shot "start the opening" flag through router state; the play screen fires the opening turn,
which writes no player row. A second enter is refused by the server, and the flag is cleared with a
replacing navigation so a reload cannot fire it again.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | "Start adventure" is live on the current unplayed row of the run screen: it enters the adventure and opens the play screen with the opening flag; busy and error states | enabled only when the party is ready; pressing enters and navigates with the flag; an already-active adventure still navigates; a network error shows a retryable line | – |
| 2 | frontend | The play screen can fire the opening turn once: the turn hook gains a no-text send that shows no player row, and a one-shot hook reads and clears the router flag | opening send posts no text and sets no pending row; the flag fires exactly once per mount, is cleared from history, and nothing fires without it | – |
| 3 | frontend | The transcript shows the empty line while only scene dividers are recorded, above the thinking line | empty line with zero rows; with only dividers; absent once any other row exists; ordered before the thinking line | – |
| 4 | frontend | The play screen wires the opening trigger; both module READMEs updated | landing with the flag fires the opening turn once and shows the thinking line; landing without it fires nothing | WI1–3 |

One owner per file; only WI4 edits READMEs.

## Interfaces
- I1 `useEnterAdventure(runId: string) → { start(): void; isPending: boolean; isError: boolean }` — `POST /api/v1/playthrough/campaign/{runId}/adventure` (no body); a 409 `ADVENTURE_ACTIVE` counts as success. On success: invalidate `["runOverview", runId]` and `["playTable", runId]`, then `navigate(`/runs/${runId}/play`, { state: { startOpening: true } })`. The button is enabled on the current `unplayed` row only while `partyReady`, disabled while `isPending`; `isError` shows `common:errors.network` inline in the section and pressing again retries.
- I2 `useTakeTurn({runId, rows}) → { send, startOpening, isSending, pending }`. `startOpening(): void` posts `{ text: null }`, sets **no** `pending` (no player row, ← AC2) and settles exactly like `send`.
- I3 `useOpeningTurn(onStart: () => void): void` — when `useLocation().state?.startOpening` is true, replaces the current history entry with the state cleared and calls `onStart()` exactly once per mount (ref-guarded, so a re-render or a double mount cannot fire twice).
- I4 `Transcript` keeps its props; the empty line renders when every row is a `divider`, below the dividers and above the thinking line.
- I5 In the play screen: `const { send, startOpening, ... } = useTakeTurn(...)` then `useOpeningTurn(startOpening)`. `turnRunning` and the composer state are unchanged.

## Acceptance tests (qa)
No end-to-end runner is configured. Component tests: AC1 → WI1, WI3, WI4 · AC2 → WI2, WI4 · AC3 → WI1 (already built server-side, asserted in the run screen test) · AC4 → WI2 · AC5 → WI1 (no character prompt on the path). The sprint lead checks the running screen in a browser before shipping.

## Order
WI1–WI3 in parallel, WI4 after.
