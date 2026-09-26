# play

The play screen (sprint 010/06): the Dungeon Master's table, one adventure at
a time. `playthrough` stays the lobby (`docs/architecture.md:28,36`); this
module owns everything past "Start adventure" / "Continue".

## Owns (WI1 — foundation)

- `transcript.ts` — `toTranscriptRows(events: EventRead[], heroName: string):
  TranscriptRow[]`, pure, no `t()` call anywhere in it. One of five row
  shapes per recorded, player-visible event, or no row at all:
  - `narration` — `narration` and `question` alike (a question's `options`
    are dropped here; no choice buttons this sprint, ← research.md
    Assumptions).
  - `player` — `player_action`; `author` is always the passed-in
    `heroName`, since the wire payload names no actor (one hero per run,
    D9) and `heroes[0].name` lives on the table read, not the transcript.
  - `system` — `rule_looked_up`, `item_moved` (`key` picked by `movement`:
    `taken`/`dropped`/`given` → `itemTaken`/`itemDropped`/`itemGiven`),
    `hp_changed`, `way_opened`, `roll_requested` (`key: "check"`, no
    difficulty — never recorded, never invented). `key` is the bare
    `SystemKey`; the row-drawing component looks the wording up at
    `system.<key>` in `play.json`. `check`'s `values` also carry a
    `context` (`"full"` when the request names both an ability and a skill,
    absent when it names an ability alone, `"kind"` when it names neither —
    attack/damage/initiative/custom rolls, the common case for those kinds,
    not an edge one) for `SystemLine`'s own `t(key, values)` call to pick
    `play.json`'s `check_full`/`check`/`check_kind` string with — i18next's
    own context selection, never a sentence composed outside `play.json`
    (AC3 fix: a missing skill or ability must never render as stray empty
    brackets).
  - `dice` — `roll`. `breakdown` joins `faces` and appends the signed
    `modifier` (`"13 + 1"`). `label` prefers the linked `roll_requested`'s
    `context.skill`, then `.ability`, then falls back to the roll's own
    `kind` (e.g. `"ability_check"`) when neither is a string or the roll
    names no request at all (an unprompted roll, D12 §1.9). The chip's
    verdict is never on this row — never recorded, never invented.
  - `divider` — `scene_entered`, only when it carries a `sceneTitle`;
    otherwise no row (older rows and mid-scene re-entries alike).
  - Anything else — `tool_call`, `adventure_started`/`_completed`,
    `system`/`error`/`warning` (Dungeon-Master-only), and any type this
    mapper does not recognise — produces no row and never throws.
- `hooks/usePlayTable.ts` — `usePlayTable(runId)` →
  `{ table, isPending, isError, notFound, retry }`, query key
  `["playTable", runId]`, over `GET …/runs/{runId}/table`. Mirrors
  `useRunOverview`'s shape exactly, 404 collapsed into `notFound`.
- `hooks/usePlayTranscript.ts` — `usePlayTranscript(runId, heroName)` →
  `{ rows, awaiting, isPending, isError, retry }`, query key
  `["transcript", runId]`, over `GET …/campaign/{runId}/events` with
  `limit: 500` (the whole transcript). `rows` is `toTranscriptRows` applied
  to the response; `awaiting` is passed through verbatim
  (`"none" | "roll:<id>" | "answer:<id>"`). `heroName` is a parameter, not a
  second read — the caller already holds it from `usePlayTable`'s
  `table.heroes[0].name`.
- `core/i18n/locales/en/play.json` — every D12 string this screen needs,
  registered as the `play` namespace in `core/i18n/index.ts`. `system.*`
  keys line up 1:1 with `SystemKey`. `"Try again"` also lives at
  `failure.retry` here, alongside `common:actions.retry` (same text, D16
  voice) — either is correct; this module's own rows never have to reach
  into `common` for it.

## Owns (WI2 — the transcript)

- `components/Transcript.tsx` — `Transcript({ rows: TranscriptRow[] })`. Draws
  D12 §2's four row kinds and no others, plus scene dividers and the empty
  line; renders nothing it wasn't given (no invented dice verdict, no
  invented check difficulty, ← sprint brief). Mounts WI3's
  `useStickToLatest()` itself and puts `scrollRef` on the scrolling element;
  `JumpToLatestPill` is rendered only while `!atBottom`.
- `components/NarrationRow.tsx`, `PlayerRow.tsx` — the Dungeon Master's and
  the player's rows; each takes its row's own fields (`text`/`at`,
  `author`/`text`/`at`) straight through, no mapping. Author strings are
  `t("narration.author")` and the passed-in hero name respectively — never
  the other way round.
- `components/SystemLine.tsx` — the only place any `system.<key>` string is
  worded: `t(`system.${systemKey}`, values)`, wrapped in D12's leading/
  trailing "·" (added here, not baked into `play.json`'s seven strings).
- `components/DiceChip.tsx` — `label`/`notation`/`breakdown`/`total` as
  given; carries no verdict mark, since one is never recorded.
- `components/SceneDivider.tsx` — the scene's name, centred, `role=
  "presentation"` (MUI's own guidance for a Divider that wraps text).
- `components/formatClockTime.ts` — the "21:02"-style clock read `Narration`/
  `PlayerRow` share, `Intl.DateTimeFormat` only (no date library).

## Owns (sprint 010/07 — taking a turn)

- `components/Composer.tsx` — `Composer({ state, onSend })`,
  `state: "open" | "turnRunning" | "awaitingChoice" | "awaitingRoll"`. Open
  renders a real text-field-and-Send form, submitting on Enter or the
  button; `onSend` never fires on empty or untrimmed text. Every other
  state renders one muted, centred, in-voice line with nothing clickable —
  a running turn, a pending question or a pending roll already say what is
  happening, so the field stays closed rather than accepting words nobody
  can act on yet.
- `components/ThinkingLine.tsx` — the "Dungeon Master is thinking" line: a
  small spinner plus one wording, wrapped in `aria-live="polite"` so
  assistive tech announces it once without interrupting anything else being
  read. It only draws the line; the caller decides when a turn is running
  and mounts it only then.
- `components/Transcript.tsx` — also takes an optional `thinking` flag
  (`TranscriptProps`); when true it renders `ThinkingLine` at the foot of
  the scroll container, below every row already recorded, so rolls and
  system lines stay above it as they land.
- `hooks/useRunNotices.ts` — `useRunNotices(runId, onTick)` opens
  `GET …/campaign/{runId}/stream` as an `EventSource` (`withCredentials`,
  cookie auth), calls `onTick` once per `updated` notice, and reopens
  itself a couple of seconds after a fatal close — an ordinary server close
  (the server ends every stream after five minutes) is left to the
  browser's own built-in reconnect.
- `hooks/usePlayTranscript.ts` — also exposes `turnUnfinished`: true when
  the last recorded event is not the closing `narration` (a turn writes its
  `player_action` first and its `narration` last, everything else lands in
  between), false on an empty transcript. Also takes an `isSendingRef`
  option and re-reads itself every few seconds (`refetchInterval`, override
  via `pollIntervalMs`) for as long as that ref reads true or the read
  itself still looks mid-turn — a fallback for when the notice stream drops
  or delays a tick (sprint 010/07 round 2, ← AC2/AC4). The read itself is
  bounded by its own deadline (`transcriptTimeoutMs`, default 15s,
  `AbortSignal.timeout` combined via `AbortSignal.any` with TanStack's own
  per-fetch signal) so a hung connection cannot wedge it forever (defect A
  round 2).
- `hooks/useTakeTurn.ts` — `useTakeTurn({ runId, rows }) →
  { send, isSending, pending }`, the one write behind a turn
  (`POST …/game/runs/{runId}/turn`). `send` shows the player's words at once
  rather than waiting on the network: it snapshots the row ids already on
  screen, opens `pending` with the text and a timestamp taken then and
  there, and only after that fires the mutation. `pending` clears itself
  once the real `player_action` row lands in `rows` (an id the snapshot
  didn't have) or the moment the mutation settles at all, so a failed turn
  never leaves a ghost row behind. Either way, settling invalidates the
  transcript query with `cancelRefetch: true` so the next read picks up
  whatever the turn actually recorded, even if an older, pre-settle read is
  still in flight (defect A round 2: `cancelRefetch: false` let a stale
  read swallow the invalidation and leave the screen stuck showing
  "thinking" after a long turn).

  `PlayRoute` composes these into the play screen: it appends `pending` (if
  any) to `usePlayTranscript`'s own rows as one more `player` row before
  handing them to `Transcript`, subscribes to `useRunNotices` to invalidate
  the same transcript query (`cancelRefetch: true`, same reasoning) on
  every server tick, and derives the composer's state and the thinking line
  from the same two reads — `awaiting` picks `awaitingRoll`/`awaitingChoice`
  outright; otherwise a turn counts as running while the mutation is in
  flight (`isSending`) or, after a reload mid-turn with nothing pending,
  while `turnUnfinished` is still true — and that one `turnRunning` flag
  drives both the transcript's `thinking` prop and the composer's
  `"turnRunning"` state together, so either always mirrors the other. The
  header's scene line (D12 §2) reads the transcript's own latest `divider`
  row in preference to the table read's `scene` (`usePlayTable.ts`, fetched
  once and never invalidated by a turn), falling back to the table read
  only while the transcript carries no scene marker yet — so entering a new
  scene mid-session updates the header the same turn it happens, not only
  after a reload (defect B).

## Owns (sprint 010/08 — start adventure, and the opening scene)

- `hooks/useTakeTurn.ts` — also exposes `startOpening()`: posts the opening
  turn (`{ text: null }`, no player row — the wire writes no `player_action`
  event for this turn kind) through the same mutation `send` uses, so it
  shares `isSending`, the settle behaviour and the transcript invalidation.
- `hooks/useOpeningTurn.ts` — `useOpeningTurn(onStart: () => void): void`
  fires `onStart` exactly once when `useLocation().state` carries
  `{ startOpening: true }` (set by `playthrough`'s "Start adventure" flow,
  `useEnterAdventure.ts`), then clears that flag with a replacing navigation
  so a reload of the same history entry never refires it. `PlayRoute` calls
  it with `startOpening`.
- `components/Transcript.tsx` — the empty line
  ("Nothing written down yet...") now shows whenever the transcript holds
  only scene dividers, not only when it holds zero rows — a brand-new
  adventure's first `scene_entered` row lands before the opening turn's
  narration does.

## Owns (sprint 010/09 — choices and rolls are buttons)

- `transcript.ts` — also exports `PendingPrompt` (`{ kind: "choice", id,
  options }` or `{ kind: "roll", id, notation }`) and `toPendingPrompt(events,
  awaiting)`, which resolves the events read's `awaiting` marker against the
  same `events` into the one prompt the buttons below act on. `null` for
  every case that is not a clean match (`"none"`, a stale/missing id, the
  marker's prefix pointing at the wrong event type, an empty `options`),
  same never-throw stance as `toTranscriptRows`. A `roll`'s dice row also now
  carries a `verdict` (`"madeIt"` / `"missed"`) once its linked
  `roll_requested`'s `context.dc` is known, and the check line itself shows
  that same `dc` — both left off entirely, never guessed, when no DC was
  ever recorded.
- `hooks/usePlayTranscript.ts` — also exposes `pending: PendingPrompt | null`,
  `toPendingPrompt` applied to the same read; the fallback poll's own
  "still running" check already excludes a pending question or roll (it only
  fires while `isSendingRef` reads true or `awaiting === "none"`), so the
  poll stays stopped while the buttons below wait on the player.
- `components/PendingPrompt.tsx` — `PendingPrompt({ prompt, onChoose,
  onRoll })`. A `choice` prompt draws one button per option, its text
  verbatim off the wire; a `roll` prompt draws exactly one button, labelled
  `roll.button` with the notation interpolated in. The only way to answer
  while a prompt is open — no free-text field, nothing here calls the
  network itself.
- `components/Transcript.tsx` — also takes an optional `prompt` node
  (`TranscriptProps`), rendered before the thinking line so a pending
  prompt and a running turn's spinner never show at once.
- `hooks/useTakeTurn.ts` — also exposes `roll()`: posts `{ text: null }`
  through the same mutation `startOpening` uses (same settle behaviour, no
  optimistic row — the server rolls itself and this route writes no player
  row either).
- `PlayRoute` composes `pending` (from `usePlayTranscript`) and `roll` (from
  `useTakeTurn`) into the transcript's `prompt` slot: shown as soon as a
  prompt exists and nothing is sending, gone the instant `send`/`roll` is
  called even before the transcript re-read catches up, since a stale read
  still names the same prompt for a moment otherwise. The composer's state
  now picks in this order: `isSending` first (→ `"turnRunning"`, so the
  buttons and the field alike are gone the moment a click fires), then
  `awaiting`'s `roll:`/`answer:` prefix (→ `"awaitingRoll"`/
  `"awaitingChoice"`), then the plain running/open split sprint 010/07 WI6
  already had. Reloading mid-prompt shows the same buttons, since both
  `pending` and `awaiting` come straight off the transcript read.

## Owns (defect fix — a finished run closes the play screen)

- `transcript.ts` — a sixth row kind, `"ending"` (`{ kind: "ending", id,
  outcome }`), mapped from a `system` event whose `details.outcome` is one
  of `finish_run`'s own three values (`victory`/`defeat`/`authored`); a
  `system` event carrying no such field (e.g. the "already finished"
  refusal) still produces no row.
- `components/EndingDivider.tsx` — the transcript's closing marker, styled
  like `SceneDivider`, worded through `ending.<outcome>` in `play.json`.
- `PlayRoute` reads `table.runStatus === "finished"` (not the transcript's
  own `ending` row, which a reload can race) to replace the composer with a
  permanent closed line (`composer.closed`) plus a link back to the
  campaign (`end.button`), instead of the turn-in-progress composer states.

## Surface

- `TranscriptRow`, `SystemKey`, `EventRead` (re-exported) — consumed by
  WI2's row components.
- `PlayTable` (re-exported `TableRead`) — consumed by WI4's header/party
  rail.
- `Transcript` — consumed by WI4's play screen route.
- WI3 (stay-at-latest) and WI4 (the screen itself) build on top of this file
  set in parallel, per sprint 010/06's plan.
- `Composer`, `useRunNotices`, `useTakeTurn` and `usePlayTranscript`'s
  `turnUnfinished` — consumed by `routes/PlayRoute.tsx` (sprint 010/07 WI6)
  to drive sending a turn, live updates and the composer/thinking state.
- `useOpeningTurn` and `useTakeTurn`'s `startOpening` — consumed by
  `routes/PlayRoute.tsx` (sprint 010/08 WI4) to fire the opening turn once
  when the route is reached from `playthrough`'s "Start adventure" flow.
- `usePlayTranscript`'s `pending`, `useTakeTurn`'s `roll`, and
  `PendingPrompt` — consumed by `routes/PlayRoute.tsx` (sprint 010/09 WI5) to
  show the answer/roll buttons in the transcript's `prompt` slot and drive
  the composer's `awaitingChoice`/`awaitingRoll` states.
