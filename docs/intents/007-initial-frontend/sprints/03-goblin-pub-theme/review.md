---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/43
---
# Review: Sprint 03 — The Goblin Pub look and the new name

## What changed
The product is now called The Goblin's Tavern and wears the delivered dark tavern look: lantern amber on
deep loam, the design's serif and small-caps lettering, and panels whose corners are subtly uneven. Nothing
a visitor can do has changed — only how it looks and what it calls itself.

## How to check it
- Open sign-in: dark page, small-caps wordmark above the card, amber button — no blue anywhere.
- Follow "Create an account": same look, same wording and hints as before.
- Sign in: the header carries the new name; the greeting is set in the display serif.
- The browser tab reads "The Goblin's Tavern" on each of those pages.
- There is no light mode to find, whatever the device is set to.

## Heads-up
- The interactive API page still shows the old name: that title comes from the server side, which this
  sprint was not allowed to touch. Finishing the rename there is a small separate change.
- The sign-out control's focus outline is a faint fill rather than the crisp ring the design shows. The
  header and account menu are rebuilt next sprint, the right place to settle it.
- The lettering ships with the product instead of being fetched from an outside font service, so it
  renders identically offline.

Brief: docs/intents/007-initial-frontend/sprints/03-goblin-pub-theme/brief.md

## Verdict
Round 1: approve — Signing in, signing up and the landing page all wear the dark tavern look now — amber
on deep green-black, with the serif and small-caps lettering — and the product calls itself The Goblin's
Tavern in the header and in the browser tab. Nothing shows the old blue anywhere, and the pages stay dark
even when the device asks for light mode. Everything still behaves as before: a wrong password still
explains itself, creating an account still lands you on the welcome page, and signing out still returns
you to sign-in.
