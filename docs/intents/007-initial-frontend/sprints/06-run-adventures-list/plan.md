---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 06

Frontend only, one work item. The run overview read from sprint 02 already carries `adventures[]`; sprint 05 ignored it.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | An adventures section on the run screen: one numbered row per adventure with title, teaser and status badge in campaign order; the first unplayed one reads "Next up" when every character is ready and "Waiting on party" with the reason otherwise and carries a disabled "Start adventure"; later rows read "Locked", finished ones "Done" | order and numbering; next-up vs waiting-on-party by party readiness; locked and done rows; the button renders, is disabled and calls nothing | – |

## Interfaces
- I1: `modules/playthrough/components/AdventuresSection.tsx`, consumed by `RunRoute.tsx` directly after `<PartySection …>`
  ```ts
  import type { RunOverview, RunMember } from "../hooks/useRunOverview";
  type RunAdventure = RunOverview["adventures"][number]; // id, title, introExcerpt, status
  export function AdventuresSection(props: { adventures: RunAdventure[]; members: RunMember[] }): ReactElement;
  ```
- I2: the state rules, derived in the browser from fields the API supplies — no invented status
  ```ts
  const partyReady = members.length > 0 && members.every((m) => m.ready);
  const currentIndex = adventures.findIndex((a) => a.status !== "done");   // -1 → every adventure done
  //   a.status === "done"  -> "adventures.status.done"
  //   i === currentIndex   -> partyReady ? "adventures.status.nextUp" : "adventures.status.waitingOnParty"
  //   otherwise            -> "adventures.status.locked"
  // "Start adventure" renders on row `currentIndex` only, always disabled, no onClick.
  ```
- API: `CampaignRunAdventureRead` = `id, title, introExcerpt, status`; `status` ∈ `done | active | unplayed`; the array arrives in campaign order — render as received, never sort. `introExcerpt` is the teaser, already clipped server-side.
- i18n: WI1 owns `playthrough:adventures.*` exclusively; `run.*` and `party.*` stay sprint 05's.

## Acceptance tests (qa)
No separate qa agent — the sprint is one component with no seam, and sprint 05 set the precedent of a thin suite plus a browser pass.
- AC1–AC4 → cases added to the existing `RunRoute.test.tsx`, whose fixture currently sends `adventures: []`.
- AC5 → read as "no status literal is invented": covered by the badge cases plus a browser pass on the preview site.

## Order
WI1 alone.
