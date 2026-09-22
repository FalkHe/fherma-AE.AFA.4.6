---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 08

Frontend only, one work item. Filtering is client-side over sprint 07's existing list read — no backend change,
no new query parameter.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | Three tags above the run list — "In progress", "New", "Archived" — that filter it; archived cards muted, buttonless and unopenable under a note saying archived runs are kept as they are; the dashboard opens on "In progress", falls back to "New", and with no runs shows the invitation and no tags; an empty tag shows a short line, not the invitation | each tag shows only its own runs; archived card has no link and cannot be opened; opening tag is In progress, else New; no runs → invitation, no tags; an empty tag shows its own line; the chosen tag is never persisted | – |

## Interfaces
```ts
// runStatus.ts — the tag set IS the existing RunStatusKey; no second mapping, so a card's badge
// and its tag cannot disagree. Labels stay run.status.new/.inProgress/.archived.
export function runActionKey(status: string): "dashboard.card.begin" | "dashboard.card.resume" | null;
//   → null exactly when runStatusKey(status) === "run.status.archived"   (AC3)

// DashboardRoute.tsx — AC4/AC5
const TAGS: RunStatusKey[] = ["run.status.inProgress", "run.status.new", "run.status.archived"];
const [picked, setPicked] = useState<RunStatusKey | null>(null);   // component state only, never persisted
const defaultTag: RunStatusKey = runs.some((r) => runStatusKey(r.status) === "run.status.inProgress")
  ? "run.status.inProgress"
  : "run.status.new";
const activeTag = picked ?? defaultTag;                            // derived every render: no effect, no flicker
const visible = runs.filter((r) => runStatusKey(r.status) === activeTag);
// tags + note + list render only when runs.length > 0; otherwise the invitation alone.
```

- Status → tag, confirmed against the backend: `setup` and any unknown value → New · `ready` and `active` →
  In progress · `archived` and `finished` → Archived. This is what `runStatusKey` already computes.
- New keys under `dashboard.tags.*`: `heading`, `groupLabel`, `empty`, `archivedNote`.
- AC5 is already guarded: `structure.test.ts` fails the suite on any storage or cookie reference under `src`.

## Acceptance tests (qa)
No separate qa agent, as in sprints 05–07.
- AC1–AC5 → cases in the existing `DashboardRoute.test.tsx`. Its current AC1/AC2 case asserts an `active` and a
  `setup` card on screen together; with filtering on they never co-exist, so that case splits per tag.

## Order
WI1 alone.
