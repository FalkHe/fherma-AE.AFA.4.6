---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 04 — one guarded shell, and back to the page you asked for

## What changed
Every signed-in page now sits under one shared header with the tavern wordmark and an account button,
whose menu shows the player's name and signs them out. Sign-in is guarded in one place instead of page by
page, and opening a page while signed out sends you to sign-in, then back to that exact page.

## How to check it
- Signed out, open the dashboard address: you land on sign-in, sign-up one click away.
- Sign in there: you arrive on the dashboard you asked for, not the welcome page, address intact.
- On any signed-in page the header shows the wordmark and a round button with your initial; open it for your
  name and "Sign out". Signing out returns to sign-in; Back does not restore the page.
- Sign in again after signing out: the welcome page, not wherever you had been.

## Heads-up
- The dashboard is deliberately an empty page with a heading, so the return is visible now; sprint 07 fills it.
- One defect surfaced only in the browser: after signing out, signing back in threw you onto the last page
  you had been bounced from. Fixed and covered by a test, though that fix works by ordering one corrective
  step last — sound, but timing-based, and worth making structural next time this flow is opened up.

Brief: docs/intents/007-initial-frontend/sprints/04-guarded-app-shell/brief.md

## Verdict
