---
phase: 2
step: "2.8"
title: Backlog screen, UI-only
summary: The admin backlog route per ui-spec — status-chip table with URL-persisted filter, live-progress cell, add-model dialog, retry affordance, SSE disconnect warning — against pinned useProducts/useOperations stubs with fixture data; zero API calls.
effort: 4
dependencies: ["2.2", "2.4", "1.4"]
agent: frontend-dev
track: frontend
---

# Step 2.8 — Backlog screen, UI-only

**Effort: 4** — one route, four shared components, two stub hooks; every
layout/state decision is already made in the ui-spec.

**Required reading before any code:**
[`ui-spec.md`](ui-spec.md) §1–§5 + §10–§11 — binding, component by component.
[`shared-knowledge.md`](shared-knowledge.md) — *Frontend conventions* (hook
files, exports, **2.8 stub rule with the exact fixture set**, query keys).
Phase-1 shared-knowledge for file placement and i18n conventions. Zero
deviations; stop and report if one seems necessary.

## Files

- Create `frontend/src/routes/admin/AdminBacklogRoute.tsx`
  (**delete `frontend/src/routes/admin/AdminHomeRoute.tsx`** — explicit
  placeholder, per ui-spec §1)
- Create `frontend/src/components/AddModelDialog.tsx`,
  `MotorbikeStatusChip.tsx`, `OperationProgress.tsx`, `EmptyState.tsx`
- Create `frontend/src/hooks/useProducts.ts` (STUB),
  `frontend/src/hooks/useOperations.ts` (STUB)
- Modify `frontend/src/App.tsx` (route table),
  `frontend/src/components/AdminLayout.tsx` (tab-value `startsWith`, SSE
  disconnect Alert per ui-spec §3.3),
  `frontend/src/locales/en/translation.json` (§10 keys; replace the Phase-1
  `admin.backlog.emptyTitle/emptyBody` placeholder values)

## Implementation outline

- Stubs per the pinned rule: real `useQuery`/`useMutation` results over
  fixtures (one product per status; the `ingesting` one with a running
  40 % operation; one `backlog` row with a `failed` operation), header
  comment naming step 2.15 as the deleting step. Components must survive
  2.15 unchanged.
- Everything else is a transcription of ui-spec §2–§5: toolbar
  (filter + Add), table with the five pinned columns, `OperationProgress`
  states, `AddModelDialog` states, empty/loading/error states via
  `EmptyState`, disconnect Alert with the 5 s grace timer.
- Component tests (Vitest + the shared render helpers) for:
  `OperationProgress` state matrix, filter → URL param round-trip, dialog
  validation/pending states.

## Out of scope

- Real API calls (2.15), review screen (2.13), `ConfirmDialog` (2.13 —
  first consumer).

## Verification

- `pnpm typecheck && pnpm lint && pnpm test` green.
- At `localhost:5173/admin` (stack up, logged in as admin): fixture rows
  render incl. the progress cell and failed-row retry; filter survives
  reload via URL; all strings from `translation.json`; theme toggle works on
  every state.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
