---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 06

D12's dice chip ends in a verdict and its check line carries a difficulty, neither of which the game
writes anywhere a player can read. The screen shows the dice without the verdict for now; recording them
is proposed as its own backlog row rather than grown into this sprint.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | The two reads the screen needs, the pure translation of recorded entries into transcript rows, and every D12 string as a key | each recorded kind becomes the row D12 draws, or none at all; a scene entry becomes a divider only when it names the scene; the mapper stays pure | – |
| 2 | frontend | The transcript itself: the four kinds of row, the dice chip, the scene dividers and the empty line, in D12's layout | narration, player, system and dice rows each render as D12 draws them; system lines are worded from values by the interface's own strings; an empty transcript shows its line | WI1, I1–I3 |
| 3 | frontend | The transcript stays at the newest entry, with "Jump to the latest" when scrolled up | it loads at the newest entry; scrolling up reveals the pill; the pill returns to the newest | I2 |
| 4 | frontend | The play screen at the run's address plus a segment: header, back link, loading, error and not-found, and the narrow layout | the header shows the campaign back link, the adventure title and the scene line; back returns to the lobby; a narrow screen matches D12's narrow wireframe | WI1, I3, I4 |
| 5 | frontend | On the run screen an adventure under way reads "In progress" with "Continue" leading to the play screen | an adventure under way reads "In progress"; "Continue" opens the play screen | – |

No two work items touch the same file.

## Interfaces
- I1 — `modules/play/transcript.ts`: `toTranscriptRows(events: EventRead[], heroName: string): TranscriptRow[]`,
  pure, no `t()`:
  ```ts
  type TranscriptRow =
    | { kind: "narration"; id: string; text: string; at: string }   // also `question`
    | { kind: "player"; id: string; author: string; text: string; at: string }
    | { kind: "system"; id: string; key: SystemKey; values: Record<string, string | number> }
    | { kind: "dice"; id: string; label: string; notation: string; breakdown: string; total: number }
    | { kind: "divider"; id: string; scene: string };
  ```
  `at` = `createdAt`; `SystemKey` ∈ `ruleLookedUp | itemTaken | itemDropped | itemGiven | hpChanged |
  wayOpened | check`, each prefixed `system.`. `roll_requested` → `system.check`; `roll` → dice
  (`breakdown` = `faces` plus `modifier`; `label` from the linked request's `context.skill`/`.ability`
  when a string, else the kind's key); `scene_entered` → divider when it has a `sceneTitle`, else
  skipped; any other type (`adventure_*`, `system`, `error`, `warning`, unknown) → no row.
- I2 — `useStickToLatest()` → `{ scrollRef, atBottom, jumpToLatest }`; `JumpToLatestPill` takes
  `{ onClick }`, rendered by WI2 only when `!atBottom`. jsdom has no layout, so the hook reads
  `scrollTop` rather than using `IntersectionObserver` or `scrollIntoView`.
- I3 — `play.json` carries every D12 string: `header.back` `"‹ {{campaign}}"`, `header.scene`
  `"{{scene}} · saved as you go"`, `system.itemTaken` `"{{name}} takes the {{item}}"`,
  `system.hpChanged` `"{{name}}: {{before}} → {{after}} hit points"`, `system.wayOpened`
  `"{{name}} · {{action}}"`, `empty`, `jumpToLatest`.
- I4 — `usePlayTable(runId)` → `{ table, isPending, isError, notFound, retry }`, key `["playTable", runId]`;
  `usePlayTranscript(runId)` → `{ rows, awaiting, isPending, isError, retry }`, key `["transcript", runId]`,
  `limit: 500`; both in `useRunOverview`'s shape.

## Acceptance tests (qa)
No qa work item and no end-to-end runner: none is configured and this sprint does not introduce one. Each
work item's own component tests cover its criteria — AC1 → WI5, AC2 → WI4, AC3 → WI1 and WI2, AC4 → WI2,
AC5 → WI3, AC6 → WI4, AC7 → all. The sprint lead checks the running screen in a browser before shipping.

## Order
WI1 first. Then WI2, WI3, WI4, WI5 in parallel.
