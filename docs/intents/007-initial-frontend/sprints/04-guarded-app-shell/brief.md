---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 04: guarded app shell

## Task
Replace the per-route guard with one guarded layout wrapping every signed-in page, and move the app frame out of the
landing screen into a shared shell rendering the design's header: the wordmark and an account button opening a menu
with the player's name and sign out. Make return-to-requested-page work for a deep address, flipping sign-in to
navigate before writing the cache as the code note requires.

## Outcome
Opening a protected address while signed out lands on sign-in with sign-up one click away, and signing in returns to
that exact address, under the shared header with a working account menu.

## Acceptance criteria
- AC1: The guard is declared once for all signed-in pages, not repeated per route (← D5).
- AC2: A signed-out visitor to any protected address is sent to sign-in and, after signing in, lands on that address —
  not the landing page (← D5). An empty dashboard page ships as that second protected address.
- AC3: The header shows the wordmark "The Goblin's Tavern" and an account button whose menu carries the player's name
  and sign out; signing out returns to sign-in (← D11, D14).
- AC4: The shell no longer belongs to the landing screen; the structure test records its new home and the permitted
  import edge.
- AC5: Sign-in navigates before writing the cache, and the note asking for that change is removed.

## Decisions
← D5, D11, D14

## Assumptions
- The shell moves to a shared location now that a second screen will render it.
- The account menu reads the existing current-user query; the design's e-mail line is omitted because users have no
  e-mail, and the username is the name shown.
- No avatar image — the design's initial letter stands in.
- The dashboard page is an empty frame with a heading only; sprint 07 fills it. Added on the human's call, so that
  returning to a requested address is something you can see rather than only test.

## Out of scope
No dashboard or run-screen *content* beyond the empty page above · no backend · no redesign of the sign-in form
beyond the theme it inherits.
