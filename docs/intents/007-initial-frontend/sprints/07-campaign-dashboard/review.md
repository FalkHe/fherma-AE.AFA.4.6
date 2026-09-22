---
author: sprint
owner: human
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 07 — Signing in lands on a dashboard of the player's runs, or on an invitation to start the first one

## What changed
Signing in no longer lands on a bare greeting. The player now sees their campaigns: one card each with its artwork
slot, title, how far along it is, a teaser, when it was started and a button that opens it. A player with no
campaigns yet is invited to start one instead. The old landing page is gone.

## How to check it
- Sign in: the greeting reads "Welcome back, <your name>." with a line below counting the campaigns waiting on you.
- Each campaign card shows its title, a status word, the teaser, and "Adventure 1 of 1 · 1 player · Created 5 minutes
  ago". Newest campaign first.
- The button reads "Begin" on a campaign not yet started and "Resume" on one under way; either opens that campaign.
- Sign in as somebody with no campaigns: the list is replaced by an invitation to start the first one.
- "Create new campaign" is greyed out — picking a story arrives in a later sprint.

## Heads-up
- A campaign whose story content has been removed shows muted and explains itself instead of opening. That state
  cannot be produced on the running site without editing the database, so it is covered by tests only.
- Finished campaigns still read "Resume" and sit in the same list; sorting them under Archived is the next sprint.
- The greeting draws a thin amber outline around itself on arrival. That is the page telling screen readers and
  keyboard users where they have landed, and it is unchanged from the old landing page — but it is visible to
  everyone and was never in the design, so it is worth a decision of its own.
- The separate `/dashboard` address is gone with the old page; everything now lives at the site root.

Brief: docs/intents/007-initial-frontend/sprints/07-campaign-dashboard/brief.md

## Verdict
