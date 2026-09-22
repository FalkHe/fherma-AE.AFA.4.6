---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: draft
---
# Progress: Sprint 04

| WI | Status | Note |
|---|---|---|
| 1 | done | `App.tsx` is two pathless layout routes, guard outside the shell; `/dashboard` added as a heading-only page. Typecheck and lint green; the account-menu acceptance test now passes. Also fixed two stale tests that still asserted a bare sign-out button |
| 2 | done | `core/layout/AppShell.tsx` renders the wordmark itself from `common:app.title` as a `<p>`, a pill badge with lucide's `Flame`, the `action` slot kept; banner landmark verified, all styling from theme tokens, no `modules/` import |
| 3 | done | `AccountMenu` owns both hooks; trigger named "Account" with the initial, menu of username/divider/sign out, in-menu `role="alert"` on refusal, silent 401. `SignOutButton` gone, `HomeRoute` unwired, cases migrated. Also touched both module READMEs (WI5's file) |
| 4 | running | |
| 5 | open | |
| qa | done | 2 acceptance tests, both red on feature absence as expected: no dashboard address yet, no account menu yet (`frontend/src/returnToRequestedPage.test.tsx`, `frontend/src/accountMenu.test.tsx`) |

Status: `open | running | done | failed`

## Issues
- The sprint first stopped: its return-to-your-page criterion could not be demonstrated, because only one page sat behind sign-in and the brief ruled out adding another. The human resolved it — an empty dashboard page ships as that second address, and the brief's scope line was widened to match.
- The research ran past its length cap, the signal that this sprint is larger than one. The human chose to run it whole rather than split it.
- A failed sign-out is shown inside the open account menu rather than above the greeting, as the design's menu is where the action now lives.

## Backlog proposals

## Verify
