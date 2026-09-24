---
author: architect
owner: agent
created: 2026-09-23
updated: 2026-09-23
---
# Research: sprint 010/09 — choices and rolls as buttons

## Facts

**What the wire says is awaited.** `GET …/campaign/{runId}/events` answers `{events, awaiting}`;
`get_awaiting` (`playthrough/service.py:2893-2939`) returns `"roll:<eventId>"` for the newest
`roll_requested` in the open turn with no `roll` naming it, else `"answer:<eventId>"` for the newest
`question` with no later `player_action`, else `"none"`. **Both ids are ids of player-visible events
already in `events`** (`question` at `service.py:1305-1311`, `roll_requested` at `:1138`), so the pending
prompt is looked up by id — no "last event" guess needed. It *is* in fact always last: both tools append
the event and then `interrupt()` immediately (`game/agent/tools.py:288-302`, `:324-342`), so nothing is
written after it until the player acts.

**What the pending event carries.** `question.payload = {text, options[]}` (`playthrough/schemas.py:391`)
— the buttons' labels, game data, never i18n. `roll_requested.payload = {kind, actorId, formula, context}`
(`:363-375`): `formula` is the notation for "Roll 1d20+3"; `context` is free-form `Any`, model-supplied,
and `transcript.ts:56-63,88-116` already reads `ability`/`skill` out of it defensively.

**No DC, no verdict anywhere the player can read.** `roll_requested` has no DC field, and the DM only
names one *later*, when it spends the roll: `resolve_check`/`resolve_save` compute `success = total >= dc`
and write it on a `visibility="dm"` `tool_call` (`playthrough/service.py:1490-1509`), which `list_events`
never returns. `roll.payload` has faces/modifier/total and no DC (`schemas.py:378-389`). The DM prompt
(`game/prompts/v1/system/dm.md`, 13 lines) does not mention `request_player_roll` at all, so today's
`context` may hold anything, DC included or not. **Smallest addition: none to the schema.** `context` is
already free-form, so teaching the DM to pass `{"ability", "skill", "dc"}` when it asks for a check (one
line in `dm.md`, one in the tool docstring, `game` module) gives AC3 its "· DC {n}" and lets the chip's
mark be a client-side `total >= dc` against the *linked request's* `context.dc` — no migration, no new
event type, no `make generate-api`. Trade-off: a model that omits `dc` costs the DC and the mark, never a
wrong one; the alternative (a typed `dc` on `RollRequestedPayload`, or a new player-visible event) buys
validation at the price of a schema change in a second module, and is not worth it yet.

**Sending.** `POST /api/v1/game/runs/{runId}/turn`, body `{text}` only. A pending question →
`run_turn` kind `answer`: `text` must be one of the interrupt's `options` or it raises
`ACTION_NOT_AVAILABLE`; accepted, it appends the `player_action` row itself and resumes
(`game/service.py:237-268`) — so AC2's player row is the server's, and `useTakeTurn`'s optimistic row plus
its snapshot rule already bridge the wait (`hooks/useTakeTurn.ts:75-95`). A pending roll → kind `roll`,
`resume({"action":"roll"})`, **`text` discarded and the server rolls** (`service.py:269-280`,
`tools.py:362-368`): the client posts `{text: null}`, exactly as `startOpening` already does, and shows no
optimistic row.

**States.** `PlayRoute.tsx:120-131` derives `turnRunning = isSending || (awaiting === "none" &&
turnUnfinished)` and maps `roll:`/`answer:` onto `awaitingRoll`/`awaitingChoice` — so while a prompt
stands the thinking line is already hidden and the composer already closed (AC1, AC3). One gap: after the
press, `awaiting` still names the prompt until the re-read lands, so `isSending` must take precedence
(composer `turnRunning`, thinking line back, buttons gone — AC2, AC4).

**AC5 comes free**: `awaiting` plus the events are both re-read on mount, so the same buttons return after
a reload with no client state at all.

**i18n** (`core/i18n/locales/en/play.json`, keys compile-checked): `composer.awaitingChoice`,
`composer.awaitingRoll`, `roll.button` (`"Roll {{notation}}"`), `system.check`/`check_full`/`check_kind`
all exist. **Missing**: `dice.madeIt` `"✓ made it"`, `dice.missed` `"✗ missed"`, and the DC variants
`system.check_dc`, `check_fullDc`, `check_kindDc`. i18next context suffixes are already how this file
picks a check string (`transcript.ts:99-116` + `SystemLine.tsx`), so the new variants copy that usage.

## Work items

One owner per file; WI2 fixes the shared strings and lands first, WI3–WI5 are written against I1–I5 in
parallel.

- **WI1 backend-python** — `game/prompts/v1/system/dm.md`, the `request_player_roll` docstring in
  `game/agent/tools.py`, `game/README.md`: when asking for a check or save, pass
  `context={"ability", "skill", "dc"}`. No schema, no route, no client regeneration.
- **WI2 data and strings** — `transcript.ts`, `transcript.test.ts`, `hooks/usePlayTranscript.ts` and its
  test, `core/i18n/locales/en/play.json`: I1, I2 and the five new keys.
- **WI3 components** — new `components/PendingPrompt.tsx` (+ test) and `components/DiceChip.tsx` (+ new
  `DiceChip.test.tsx`): I3, I4.
- **WI4 transcript foot** — `components/Transcript.tsx` + its test only: I5.
- **WI5 wiring** — `hooks/useTakeTurn.ts`, `routes/PlayRoute.tsx`, both tests, `README.md`: I6.

## Interfaces

**I1 `transcript.ts`** — `dice` rows gain `verdict?: "madeIt" | "missed"` (`total >= dc` when the linked
request's `context.dc` is a number; absent otherwise). `check` rows gain `dc` in `values` and the context
variants `fullDc` / `dc` / `kindDc` beside today's `full` / — / `kind`. New export:
```ts
export type PendingPrompt =
  | { kind: "choice"; id: string; options: string[] }
  | { kind: "roll"; id: string; notation: string };
export function toPendingPrompt(events: EventRead[], awaiting: string): PendingPrompt | null;
```
`null` for `"none"`, an id not in `events`, or a question whose `options` is empty (assumption below).

**I2** `usePlayTranscript` additionally returns `pending: PendingPrompt | null`.

**I3** `PendingPrompt({ prompt, onChoose, onRoll }: { prompt: PendingPrompt; onChoose: (option: string) =>
void; onRoll: () => void })` — one button per option (labels verbatim, stacked full-width on narrow), or
one `t("roll.button", { notation })` button.

**I4** `DiceChip` gains `verdict?: "madeIt" | "missed"` — `✓`/`✗` beside the total, accessible name from
`t("dice.madeIt")` / `t("dice.missed")`; nothing drawn without it.

**I5** `Transcript({ rows, thinking, prompt }: { …; prompt?: ReactNode })` — rendered inside the scroller
after the rows, before the thinking line.

**I6** `useTakeTurn` gains `roll(): void` → the same mutation with `{ text: null }`, no optimistic row. In
`PlayRoute`: `composerState` checks `isSending` first (`"turnRunning"`), then the `awaiting` prefixes;
`prompt` is passed to `Transcript` only when `pending !== null && !isSending`, with `onChoose = send` and
`onRoll = roll`.

## Open questions

None product-visible. Assumptions, for veto: a question that arrives with no options leaves the composer
open, since the turn route accepts free text in exactly that case — a prompt with no button would
otherwise deadlock the run; a roll or check whose DC the Dungeon Master did not name shows the check line
without "· DC n" and the chip without a mark, never an invented one.
