---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 04

| WI | Status | Note |
|---|---|---|
| 1 | done | `App.tsx` is two pathless layout routes, guard outside the shell; `/dashboard` added as a heading-only page. Typecheck and lint green; the account-menu acceptance test now passes. Also fixed two stale tests that still asserted a bare sign-out button |
| 2 | done | `core/layout/AppShell.tsx` renders the wordmark itself from `common:app.title` as a `<p>`, a pill badge with lucide's `Flame`, the `action` slot kept; banner landmark verified, all styling from theme tokens, no `modules/` import |
| 3 | done | `AccountMenu` owns both hooks; trigger named "Account" with the initial, menu of username/divider/sign out, in-menu `role="alert"` on refusal, silent 401. `SignOutButton` gone, `HomeRoute` unwired, cases migrated. Also touched both module READMEs (WI5's file) |
| 4 | done | `useSignIn` navigates before writing the cache and the ordering note is deleted; `RequireAnonymous` honours the remembered address. Deep link with query and fragment verified live. Round 2 fixed the remembered address outliving its sign-in; both halves re-verified in the browser |
| 5 | done | Structure test pins `core/layout/AppShell.tsx`, narrows the `.tsx` ban to `core/layout/`, widens the `modules/` import scan to `.tsx`, shrinks the `home → auth` edge to `useCurrentUser`, and asserts the two deleted files stay gone; probes verified. `docs/architecture.md` updated |
| qa | done | 2 acceptance tests, both red on feature absence as expected: no dashboard address yet, no account menu yet (`frontend/src/returnToRequestedPage.test.tsx`, `frontend/src/accountMenu.test.tsx`) |

Status: `open | running | done | failed`

## Issues
- WI4 round 2: the remembered address outlived the sign-in that consumed it. Caught in the browser, not by tests — after signing out, a fresh visit to sign-in still landed on the last deep page. Sent back with the reproduction.
- The sprint first stopped: its return-to-your-page criterion could not be demonstrated, because only one page sat behind sign-in and the brief ruled out adding another. The human resolved it — an empty dashboard page ships as that second address, and the brief's scope line was widened to match.
- The research ran past its length cap, the signal that this sprint is larger than one. The human chose to run it whole rather than split it.
- A failed sign-out is shown inside the open account menu rather than above the greeting, as the design's menu is where the action now lives.

## Backlog proposals
- The sign-out fix clears the remembered address with a corrective navigation queued on a zero-delay timer, winning by running last. It works and is regression-tested, but it is timing-based; ordering the cache write and the navigation inside one transition would remove the timer. Worth hardening when the auth flow is next touched.

## Verify
Round 1: approve, no failed criteria. All five checked in the browser. The sign-out defect was re-attacked
four ways and held. The merge request could not be approved by button — the reviewing account authored it,
so GitLab refuses self-approval; the verdict is posted as a note (note_487). Human approval still outstanding.
