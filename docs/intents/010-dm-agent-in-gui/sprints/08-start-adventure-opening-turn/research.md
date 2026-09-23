---
author: architect
owner: agent
created: 2026-09-23
updated: 2026-09-23
---
# Research: sprint 010/08 — start adventure, and the opening scene

## Facts

**"Start adventure" today.** Rendered on the current row only, and only while it is still `unplayed`
(`AdventuresSection.tsx:182`), always `disabled`, with no `onClick` at all and a hover tooltip carrying
the waiting hint (`:123-131`). `RunRoute.test.tsx:197-214` pins that it is disabled — that assertion has
to move. `partyReady` is `members.every(m => m.ready)` (`:197`), and `ready` is "this seat has a
character" (`playthrough/service.py:482`).

**Entering and the opening turn are two calls, not one.** `POST /api/v1/playthrough/campaign/{run_id}/adventure`
(`playthrough/routes.py:141-157`, `CsrfAuth`, no body, 201 `AdventureRunRead`) runs `enter_adventure`
(`service.py:862-975`): first campaign adventure with no `adventure_runs` row, positions the cast and
**every member character** into the entry scene (`:955-963`), appends `adventure_started` and
`scene_entered`, one commit. No model call. The opening turn is then the ordinary turn route with no
text: `POST /api/v1/game/runs/{run_id}/turn`, body `{"text": null}` (`game/schemas.py:25`,
`schema.d.ts:914-917`) → kind `opening`, `record_action=False`, so no player row is written
(`game/service.py:300-311`) — AC2.

**No character, no header.** `get_table` anchors the header's adventure and scene on the caller's own
character's `adventure_run_id`/`scene_id` (`service.py:605-625`), which only `enter_adventure` sets — a
character created after entering is never positioned. This sprint creates none (brief: out of scope);
today only the creation chat's `save_character(ready_made=True)` writes the ready-made hero
(`character/agent/tools.py:389-414`).

**"Entered once" on the wire.** The run overview maps the `adventure_runs` row to `status: "active"`
(`service.py:495-515`), which `AdventuresSection.tsx:220-229,183` already renders as "In progress" +
"Continue" — AC3 is built; only invalidating `["runOverview", runId]` (`useRunOverview.ts:55`) after
entering is new. A second enter is refused server-side: `uq_adventure_runs_active` →
`AdventureActiveError` → 409 `ADVENTURE_ACTIVE` (`service.py:940-950`, `errors.py:122-136`,
`core/errors.py:69`), so a double press can neither enter twice nor skip ahead to adventure II.

**A just-entered run's transcript is not empty.** It holds two player-visible events; `scene_entered`
becomes a `divider` row, `adventure_started` no row at all (`transcript.ts:172-180`). Two consequences:
(a) `isTurnUnfinished` is already true (last event is not a `narration`, `transcript.ts:202-204`), so
`turnRunning`, the thinking line and the closed composer are on screen from the first paint and stay
there across a reload, with `usePlayTranscript`'s fallback poll running (`PlayRoute.tsx:115,170`,
`usePlayTranscript.ts:83-87`) — AC1 and AC4 need no new signal; (b) `Transcript` prints D13's empty line
only when `rows.length === 0` (`Transcript.tsx:82-86`), so that one divider suppresses it. **Smallest
fix:** print it whenever no row other than a `divider` is present, keeping the dividers above it (D12 §3,
"First entry into a brand-new adventure").

**Strings.** `play:empty` is D13's line verbatim (`locales/en/play.json`); `common:errors.network` covers
a failed start. No i18n file is edited.

**AC4's guarantee.** Nothing on the wire says a turn is in flight: `awaiting` reads `"none"` for a
running turn and a finished one alike. Server-side, `run_turn` reads the checkpoint, so a second no-text
call while the opening graph still has a step queued becomes `retry`/`invoke(None)`, never a second
opening (`game/service.py:283-292`, `thread_state`, `:156-176`) — but that is a resumed leg running
*beside* the first, and there is no turn-in-flight lock to add cheaply. So the guarantee is a one-shot
client trigger: the run screen navigates carrying router state, the play screen fires the opening once
per mount and clears that state with a replacing navigation. Clearing is required, not optional —
`navigate(to, {state})` stores the value in browser history, which a reload restores
(react-router 8.3.1, `frontend/pnpm-lock.yaml:1455`; source: context7 `/websites/reactrouter`,
`useNavigate` / `useLocation`). An opening that broke is sprint 10's retry (brief assumption).

## Work items

One owner per file, as last sprint. WI1–WI3 are disjoint and run in parallel; WI4 runs last and is the
only item touching a README.

- **WI1 Run screen** — `playthrough/hooks/useEnterAdventure.ts` (new, + test),
  `components/AdventuresSection.tsx`, `components/AdventuresSection.test.tsx` (new),
  `routes/RunRoute.test.tsx`: the enter mutation, the live button, its in-flight and error states.
- **WI2 Opening trigger** — `play/hooks/useTakeTurn.ts` (+ test) gains `startOpening`;
  `play/hooks/useOpeningTurn.ts` (new, + test) owns the one-shot router-state handshake.
- **WI3 Empty line** — `play/components/Transcript.tsx` + `Transcript.test.tsx` only.
- **WI4 Wiring and docs** — `play/routes/PlayRoute.tsx`, `PlayRoute.test.tsx`, `play/README.md`,
  `playthrough/README.md`. Written against I2–I4, not against the other items' code.

## Interfaces

- **I1** `useEnterAdventure(runId: string) → { start(): void; isPending: boolean; isError: boolean }` —
  `POST /api/v1/playthrough/campaign/{runId}/adventure` (no body); a 409 `ADVENTURE_ACTIVE` counts as
  success. On success: invalidate `["runOverview", runId]` and `["playTable", runId]`, then
  `navigate(`/runs/${runId}/play`, { state: { startOpening: true } })`. The button is enabled on the
  current `unplayed` row only while `partyReady`, disabled while `isPending`; `isError` shows
  `common:errors.network` inline in the section and pressing again retries.
- **I2** `useTakeTurn({runId, rows}) → { send, startOpening, isSending, pending }`. `startOpening(): void`
  posts `{ text: null }`, sets **no** `pending` (no player row, ← AC2) and settles exactly like `send`.
- **I3** `useOpeningTurn(onStart: () => void): void` — when `useLocation().state?.startOpening` is true,
  replaces the current history entry with the state cleared and calls `onStart()` exactly once per mount
  (ref-guarded, so a re-render or a double mount cannot fire twice).
- **I4** `Transcript` keeps its props; the empty line renders when every row is a `divider`, below the
  dividers and above the thinking line.
- **I5** In `PlayScreen`: `const { send, startOpening, ... } = useTakeTurn(...)` then
  `useOpeningTurn(startOpening)`. `turnRunning` and the composer state are unchanged.

## Open questions

*Product-visible* — a run whose seat holds no hero at all still reads "Waiting on party" and cannot press
"Start adventure"; the only way to take the ready-made hero today is the character-creation chat. Is that
acceptable for this sprint (assumed: yes, character creation is out of scope), or should "Start
adventure" take the ready-made hero itself when the seat is empty?

*Assumptions, for veto*: the opening turn is fired from the play screen, so the header already names the
scene at first paint; a failed enter keeps the player on the lobby with a retryable line.
