---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 04

Contracts are fixed verbatim in `research.md → Interfaces` — `AppShellProps`, `AccountMenu`, the
`useSignIn` ordering and the `structure.test.ts` entries. Only the deltas are restated here.

## Work items
| WI | Agent | Deliverable | Behaviours | Depends on |
|---|---|---|---|---|
| 1 | frontend | One guard for the whole signed-in area, with an empty dashboard page behind it as a second protected address | Both pages render when signed in; signed out, each reaches sign-in; no header while the session read is pending or errored; sign-in and sign-up still bounce a signed-in visitor | 2, 3 |
| 2 | ui-designer | The shared frame wears the designed header: badge, flame mark, wordmark, and a slot for the account control | Wordmark shows and is not a heading; the bar is a banner landmark; no colour or radius literal | – |
| 3 | frontend | An account menu carries the player's initial, their name and sign out | Trigger named "Account" showing the initial; menu holds username and "Sign out"; signing out lands on sign-in, Back does not restore the page; a refused sign-out keeps them signed in and says so in the open menu; an expired session signs out silently | – |
| 4 | frontend | Signing in returns the visitor to the address first asked for | From the dashboard, sign-in ends there, not on the landing page; a direct sign-in still ends on the landing page; query and fragment survive | 1 |
| 5 | frontend | The structure test and module notes record the frame's new home and the permitted import edge | An unpinned file under core, or a forbidden cross-module import, fails it | 1, 2, 3 |
| qa | qa | Acceptance tests | below | – |

## Interfaces
- I1 — `research.md → Interfaces`, unchanged: WI2 owns `core/layout/AppShell.tsx` (deleting the `home` copy), WI3 owns `modules/auth/components/AccountMenu.tsx` (deleting `SignOutButton.tsx`), WI4 owns `useSignIn.ts` and `RequireAnonymous`, WI5 alone edits `structure.test.ts`, both module `README.md`s and `docs/architecture.md`.
- I2 — **delta:** WI1 also creates `modules/home/routes/DashboardRoute.tsx`, a heading only, its copy through a new key `home:dashboard.title`; sprint 07 fills it. The signed-in layout route therefore carries two children, guard **outside** the shell so no header flashes while the session read is pending:
  ```tsx
  <Route element={<RequireAuth><AppShell action={<AccountMenu />}><Outlet /></AppShell></RequireAuth>}>
    <Route path="/" element={<HomeRoute />} /><Route path="/dashboard" element={<DashboardRoute />} />
  </Route>
  ```
- I3 — **delta:** WI4's deep-link target is `/dashboard`; `research.md`'s note that AC2 needs a second address is now met.

## Acceptance tests (qa)
- AC2 → signed out at the dashboard, sign-in returns there, not to the landing page.
- AC3 → the header names the product; the account menu carries the player's name and signs them out.
- AC1/AC4/AC5 → the structure test and the suite; not duplicated here.

## Order
Parallel: WI2, WI3, qa. Then WI1 → WI4 → WI5.
