---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 09

What is waiting is read from the transcript: `awaiting` names the pending event by id, and that event
(a question with its options, or a roll request with its notation) is already in the transcript read. So
the buttons are derived, survive a reload, and nothing is kept client-side. The server rolls. The
difficulty and the made-it mark need one backend change: the Dungeon Master is told to name ability, skill
and difficulty when calling for a roll; the screen compares the total against it.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | When calling for a check the Dungeon Master passes ability, skill and difficulty in the roll request's context | prompt and tool docstring say so; existing game tests still pass | – |
| 2 | frontend | The transcript read tells what is pending; check rows carry the difficulty, dice rows a made-it/missed verdict; the missing strings | pending derived for a question and a roll, null for none/unknown/no options; verdict from total against difficulty; difficulty variants of the check line | – |
| 3 | frontend | The pending prompt: answer buttons or one roll button; the dice chip shows the verdict mark | one button per option, verbatim; one roll button naming the notation; chip marks made-it/missed and draws nothing without a verdict | – |
| 4 | frontend | The transcript renders a prompt slot after the rows and before the thinking line | slot rendered in that order; absent when not given | – |
| 5 | frontend | Wiring: pressing an answer sends it as the player's words, pressing roll asks the server to roll; the composer closes with its line while something waits, the thinking line returns once sent; README | choice → send, roll → roll, prompt hidden and thinking shown while sending; composer state order; reload keeps the buttons | WI2–4 |

One owner per file; only WI1 edits the game README, only WI5 the play README.

## Interfaces
- I1 `transcript.ts` — `dice` rows gain `verdict?: "madeIt" | "missed"` (`total >= dc` when the linked request's `context.dc` is a number; absent otherwise). `check` rows gain `dc` in `values` and the context variants `fullDc` / `dc` / `kindDc` beside today's `full` / — / `kind`. New export:
  ```ts
  export type PendingPrompt =
    | { kind: "choice"; id: string; options: string[] }
    | { kind: "roll"; id: string; notation: string };
  export function toPendingPrompt(events: EventRead[], awaiting: string): PendingPrompt | null;
  ```
  `null` for `"none"`, an id not in `events`, or a question whose `options` is empty.
- I2 `usePlayTranscript` additionally returns `pending: PendingPrompt | null`.
- I3 `PendingPrompt({ prompt, onChoose, onRoll }: { prompt: PendingPrompt; onChoose: (option: string) => void; onRoll: () => void })` — one button per option (labels verbatim, stacked full-width on narrow), or one `t("roll.button", { notation })` button.
- I4 `DiceChip` gains `verdict?: "madeIt" | "missed"` — `✓`/`✗` beside the total, accessible name from `t("dice.madeIt")` / `t("dice.missed")`; nothing drawn without it.
- I5 `Transcript({ rows, thinking, prompt }: { …; prompt?: ReactNode })` — rendered inside the scroller after the rows, before the thinking line.
- I6 `useTakeTurn` gains `roll(): void` → the same mutation with `{ text: null }`, no optimistic row. In `PlayRoute`: `composerState` checks `isSending` first (`"turnRunning"`), then the `awaiting` prefixes; `prompt` is passed to `Transcript` only when `pending !== null && !isSending`, with `onChoose = send` and `onRoll = roll`.
- Strings (WI2 adds to `play.json`): `dice.madeIt`, `dice.missed`, `system.checkFullDc`, `system.checkDc`, `system.checkKindDc` (existing: `composer.awaitingChoice`, `composer.awaitingRoll`, `roll.button`, `system.check*`).

## Acceptance tests (qa)
No end-to-end runner. Component tests: AC1 → WI3, WI5 · AC2 → WI5 · AC3 → WI2, WI3 · AC4 → WI2, WI3, WI5 · AC5 → WI2 (derivation from the read alone). The sprint lead checks the running screen in a browser before shipping.

## Order
WI1–WI4 in parallel; WI5 after WI2–WI4.
