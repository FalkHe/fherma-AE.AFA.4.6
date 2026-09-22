---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 07

| WI | Status | Note |
|---|---|---|
| 1 | done | dashboard, run cards, empty state; home retired; round 2 restored two lost guard tests |
| qa | – | folded into WI1's route tests |

Status: `open | running | done | failed`

## Issues
- Sprint lead merged the architect's two work items into one: building the dashboard and retiring the old landing page are the same edit, and AC6 is only checkable once the new screen exists.
- Two copy calls decided rather than referred up: with no runs the greeting carries no counting subtitle and the invitation card states the message instead; and the card's meta line counts the adventure the party is *on*, so a fresh run reads "Adventure 1 of 8" rather than "0 of 8".
- `/dashboard` as a second guarded address is retired with the old module; `/runs/<id>` already proves the guard covers more than one address, and the two acceptance tests that deep-linked it now deep-link there.

## Backlog proposals
- The empty-state invitation reuses the populated dashboard's footer copy word for word and never says "your first" — D8 asks for a distinct welcome.
- An archived run would still show a "Resume" button, against D11's "archived cards have no button". Not reachable today (no archive UI); carry into sprint 08.
- The greeting draws a visible focus outline on every arrival — inherited from the retired landing page, never in the design, and visible to everyone rather than only keyboard users.
- The revealed explanation on an unavailable card has no `aria-expanded` or live region, so a screen-reader user is not told it appeared.

## Verify
Round 1: changes requested — deleting the old landing page took two auth-guard regression tests with it (session expired, server unreachable); no acceptance criterion failed.
Round 2: approve — the two cases were restored verbatim in `modules/auth/components/RequireAuth.test.tsx` and confirmed non-vacuous by deliberately regressing the guard four ways.
