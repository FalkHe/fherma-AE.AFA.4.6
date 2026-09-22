---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
stage: draft
---
# Progress: Sprint 06

| WI | Status | Note |
|---|---|---|
| 0 | done | readyMadeName on every reply, client regenerated |
| 1 | done | page, hook, panel, dialog, locale, run-screen link, 6 tests |

Status: `open | running | done | failed`

## Issues
- The ready-made offer needs the hero's name for its button (D16); the reply gains `readyMadeName` in this sprint instead of deferring to 07.
- Browser Back is not intercepted by the leave dialog (declarative router); in-app exit link and reload/close are. Nothing is lost that leaving would not discard.
- A reload of the creation page starts a fresh conversation (nothing stored in the browser, D12).
- The wireframe's campaign-title back link becomes a plain "Back to the run" key (no cross-module import).
- glab is signed in as f4lkh3; human instruction: merge on my own when the sprint went without bigger issues, rebase from main before starting and before each merge.

## Backlog proposals

## Verify
