---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 07

Frontend only. The list read already returns every field AC2 needs, newest first — no backend change.

One work item, not the architect's two: the dashboard and the retirement of the old landing page are the same edit
seen from two sides (AC6 is only checkable once the new screen exists), and splitting them would buy an interface
contract and a coordination round for nothing. The human asked for the least-effort path.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | The signed-in landing address shows a dashboard: a greeting and a run-counting subtitle, one card per run (cover placeholder, campaign title, status badge, teaser, an "Adventure n of m · k players · Created …" line, and a Begin/Resume button opening the run screen), newest first, plus a "Start a new campaign" card; with no runs, the invitation replaces the list; a run whose content is gone is muted, cannot be opened and explains itself; the old landing screen is gone and nothing imports it | runs render newest first, one card each; Begin vs Resume by status; a card opens its run screen; the empty state replaces the list; an unavailable run is muted, explains itself and navigates nowhere; nothing imports the deleted module | – |

## Interfaces
Internal to the work item, but fixed so the suite and the run screen keep agreeing:
```ts
// modules/playthrough/routes/DashboardRoute.tsx — App.tsx renders it at "/"
export function DashboardRoute(): ReactElement;

// modules/playthrough/hooks/useRunSummaries.ts
export type RunSummary = components["schemas"]["CampaignRunSummaryRead"];
export function useRunSummaries(): {
  runs: RunSummary[];        // [] until loaded; server order kept, never re-sorted
  isPending: boolean; isError: boolean; retry: () => void;
};                           // queryKey ["runSummaries"], unwrap() like useRunOverview.ts

// modules/playthrough/runStatus.ts — RunRoute.tsx switches to it
export type RunStatusKey = "run.status.new" | "run.status.inProgress" | "run.status.archived";
export function runStatusKey(status: string): RunStatusKey;   // sprint 05's mapping, unchanged
export function runActionKey(status: string): "dashboard.card.begin" | "dashboard.card.resume";
```
The greeting is the page's single `<h1>`, `tabIndex={-1}`, focused on mount, rendered from `dashboard.greeting`
**independently of the run-list query state** — that is what keeps the existing sign-in focus pin and the guard
suites green with only copy changed. Every suite that renders `/` stubs `GET /api/v1/playthrough/runs`.

- API: `GET /api/v1/playthrough/runs` → `CampaignRunSummaryRead[]` = `id, campaignId, status, createdAt,
  campaignTitle, campaignSummary, adventuresCompleted, adventuresTotal, playerCount, unavailable`. Already newest
  first (ULID order, archived included) — never sort in the browser. `unavailable: true` ⇒ title, summary and
  `adventuresTotal` are null while both counts stay real.
- i18n: this sprint owns `playthrough:dashboard.*`; `run.*` and `party.*` and `adventures.*` stay as they are.
- Relative dates: `Intl.RelativeTimeFormat` with `{ numeric: "auto" }`, locale from `i18n.language`. No date library.

## Acceptance tests (qa)
No separate qa agent, as in sprints 05 and 06.
- AC1–AC5 → cases in a new `DashboardRoute.test.tsx`, with a fixed clock for the relative date.
- AC6 → the existing structure test plus the fact that the suite compiles with the module deleted.

## Order
WI1 alone.
