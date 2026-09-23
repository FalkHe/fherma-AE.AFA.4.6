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
    `system.<key>` in `play.json`.
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

## Surface

- `TranscriptRow`, `SystemKey`, `EventRead` (re-exported) — consumed by
  WI2's row components.
- `PlayTable` (re-exported `TableRead`) — consumed by WI4's header/party
  rail.
- `Transcript` — consumed by WI4's play screen route.
- WI3 (stay-at-latest) and WI4 (the screen itself) build on top of this file
  set in parallel, per sprint 010/06's plan.
