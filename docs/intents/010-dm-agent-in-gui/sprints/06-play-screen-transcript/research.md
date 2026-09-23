---
author: fhit:architect
owner: agent
created: 2026-09-23
---
# Research: sprint 010/06 — play screen, reading

## Facts

**Routing.** `App.tsx:30-32` registers `/`, `/runs/:runId` and `/runs/:runId/create-character`
inside one `RequireAuth` + `AppShell` layout route; `main.tsx:29-38` supplies router, theme,
i18next and react-query. The play screen is one more line there: **`/runs/:runId/play`**.

**Run screen.** `RunRoute.tsx:35` makes one read, `useRunOverview` →
`GET …/runs/{run_id}/overview` (`hooks/useRunOverview.ts:34`). Adventure
rows are `components/AdventuresSection.tsx:167-211`, the badge picked at `:190-197` from
`adventure.status` (`done | active | unplayed`, `schemas.py:125-135`); "Start adventure" is
hard-disabled at `:109-117`. `active` is not told apart from `unplayed` today — AC1 changes
those two places plus `locales/en/playthrough.json:30-40`.

**Transcript read.** `GET /api/v1/playthrough/campaign/{runId}/events`
(`backend/app/modules/playthrough/routes.py:197-216`) answers
`{events: [{id, type, turnId, payload, createdAt}], awaiting}` (`schemas.py:217-239`;
`schema.d.ts:702-733`). `service.list_events:2861-2890` returns `visibility="player"` rows
only, oldest first by id; `after` is exclusive, `limit` defaults to 200, caps at 500
(`routes.py:206`). One call with `limit=500` is the whole transcript.

**Payloads** (`schemas.py`, camelCase): `narration {text}`:348 ·
`player_action {text, answersQuestionId}`:355 — **no actor** · `roll_requested {kind,
actorId, formula, context}`:363, `context` free-form and model-supplied ·
`roll {requestId, kind, actorId, formula, faces[], modifier, total}`:378 — **no DC, no
pass/fail** · `question {text, options[]}`:391 · `scene_entered {adventureRunId, sceneId,
sceneTitle?}`:410 · `item_moved {movement: taken|dropped|given, actorName, itemName,
toName?}`:435 · `hp_changed {targetName, before, after, maxHp, alive, down}`:450 ·
`way_opened {actorName, objectName, action}`:464, `action` being a whole authored sentence
(`content/campaigns/greenhollow/v1/campaign.json:166`) ·
`rule_looked_up {topic}`:477, a full heading path · `adventure_started`/`_completed`:421.
DC and success live only on dm-only `tool_call` rows (`service.py:1497-1509`). Entering an
adventure writes the opening `scene_entered` with its title (`service.py:975-981`); rows
older than sprint 04 carry `sceneTitle: null`.

**Table read.** `GET /api/v1/playthrough/runs/{runId}/table` (`routes.py:86-91`) →
`{runId, runTitle, runStatus, campaignTitle, adventure {id, runId, title, status} | null,
scene {id, name} | null, heroes: CharacterRead[]}` (`schemas.py:161-200`;
`schema.d.ts:862-882`): back link ← `campaignTitle`, title ← `adventure.title`, second line
← `scene.name`. No hero is marked as the caller's own and `player_action` names no actor, so
the player row's name is `heroes[0].name` (one hero per run, ← D9).

**Conventions.** MUI 9.4, CSS-variable dark-only theme; colours are `var(--…)` tokens,
literals fail `structure.test.ts` (`core/theme/index.ts:16-42`). One i18n namespace per
module, registered in `core/i18n/index.ts:11-21`, keys compile-checked (`i18n.d.ts:7-11`) —
add `play` there. Vitest, `globals: false` (`vitest.config.ts:12`), the one fetch dispatcher
(`test/setup.ts:47`, `mockRoute` at `test/network.ts:50`), `renderApp`
(`test/render.tsx:91`).

**Scrolling under test.** jsdom 30.0.1 (probed in `node-cli`) has no layout:
`scrollIntoView` and `IntersectionObserver` are undefined, `scrollTop`/`scrollHeight`/
`clientHeight` read 0. Stick-to-bottom must be a ref hook over `scrollTop` and a `scroll`
listener, testable by `Object.defineProperty`.

**No end-to-end runner exists** — no Playwright config or dependency anywhere. Do not add
one here; Vitest plus the live-URL check covers this screen.

**D12 verbatim** (§4): `‹ {campaign}` · `{adventure}` · `{scene} · saved as you go` ·
divider `{scene}` · "The Dungeon Master" · `Checked the rules · {topic}` · state changes
composed by the interface ("… takes the Bent Horseshoe", "…: 12 → 9 hit points") ·
"Nothing written down yet. The Dungeon Master is opening the book." · "Jump to the latest" ·
lobby "In progress" / "Continue". Narrow (§5): one column, no rail. The screen is its own
module, `frontend/src/modules/play/`; the lobby stays `playthrough`
(← `docs/architecture.md:28,36`).

## Work items

- **WI1 foundation** (owns `modules/play/transcript.ts`, `hooks/usePlayTable.ts`,
  `hooks/usePlayTranscript.ts`, `core/i18n/locales/en/play.json`, `core/i18n/index.ts`,
  `modules/play/README.md`): the two reads, the pure wire→row mapper, the D12 strings.
  Lands first.
- **WI2 rows** (owns `modules/play/components/Transcript.tsx`, `NarrationRow`, `PlayerRow`,
  `SystemLine`, `DiceChip`, `SceneDivider`): I1's rows in D12's layout, the empty line, and
  I2's pill mounted.
- **WI3 stay-at-latest** (owns `hooks/useStickToLatest.ts`, `JumpToLatestPill.tsx`).
- **WI4 screen** (owns `routes/PlayRoute.tsx`, the new line in `App.tsx`): header, back
  link, loading / error / not-found states, narrow layout.
- **WI5 lobby** (owns `playthrough/components/AdventuresSection.tsx`,
  `locales/en/playthrough.json`, `routes/RunRoute.test.tsx`): an `active` adventure reads
  "In progress", "Continue" links to `/runs/:runId/play`.

WI2–WI5 run in parallel once I1–I4 are fixed; no two touch the same file.

## Interfaces

**I1 `modules/play/transcript.ts`** —
`toTranscriptRows(events: EventRead[], heroName: string): TranscriptRow[]`, pure, no `t()`:
```ts
type TranscriptRow =
  | { kind: "narration"; id: string; text: string; at: string }   // also `question`
  | { kind: "player"; id: string; author: string; text: string; at: string }
  | { kind: "system"; id: string; key: SystemKey; values: Record<string, string | number> }
  | { kind: "dice"; id: string; label: string; notation: string; breakdown: string; total: number }
  | { kind: "divider"; id: string; scene: string };
```
`at` = `createdAt`; `SystemKey` ∈ `ruleLookedUp | itemTaken | itemDropped | itemGiven |
hpChanged | wayOpened | check`, each prefixed `system.`.
`roll_requested` → `system.check`; `roll` → dice (`breakdown` = `faces` plus `modifier`;
`label` from the linked request's `context.skill`/`.ability` when a string, else the kind's
key); `scene_entered` → divider when it has a `sceneTitle`, else skipped; any other type
(`adventure_*`, `system`, `error`, `warning`, unknown) → no row.

**I2** `useStickToLatest()` → `{ scrollRef, atBottom, jumpToLatest }`; `JumpToLatestPill`
takes `{ onClick }`, rendered by WI2 only when `!atBottom`.

**I3** `play.json` carries every D12 string: `header.back` `"‹ {{campaign}}"`,
`header.scene` `"{{scene}} · saved as you go"`, `system.itemTaken`
`"{{name}} takes the {{item}}"`, `system.hpChanged`
`"{{name}}: {{before}} → {{after}} hit points"`, `system.wayOpened`
`"{{name}} · {{action}}"`, `empty`, `jumpToLatest`.

**I4** `usePlayTable(runId)` → `{ table, isPending, isError, notFound, retry }`, key
`["playTable", runId]`; `usePlayTranscript(runId)` → `{ rows, awaiting, isPending, isError,
retry }`, key `["transcript", runId]`, `limit: 500`; both in `useRunOverview`'s shape.

## Assumptions (veto)

- A `question` renders as a Dungeon Master row; its buttons wait for 07.
- A finished adventure keeps today's "Done" badge; D12's "Read it back" waits for 13.
- No adventure or scene on the table read (a URL typed into an untouched run) → those
  header lines are omitted; the empty transcript line carries the screen.
- `way_opened` reads `{hero} · {authored action}`; D12 gives a pattern, not this string.

## Open questions

*Product-visible*

1. D12's dice chip ends in "✓ made it / ✗ missed" and its check line carries "DC {n}",
   but neither is written anywhere the player can read — both live on the Dungeon Master's
   private rows. So the screen either shows the dice without the verdict now and a later
   sprint records them, or it waits. Default unless told otherwise: **show the dice now**.

*Technical*

- Beyond 500 entries the transcript truncates at the oldest; paging belongs with 07.
