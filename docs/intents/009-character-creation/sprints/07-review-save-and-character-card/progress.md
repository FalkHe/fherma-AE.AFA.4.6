---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
stage: done
---
# Progress: Sprint 07

| WI | Status | Note |
|---|---|---|
| 0 | done | overview carries the character; ready-made preview is a saveable review; client regenerated |
| 1 | done | ReviewPanel, save→invalidate→navigate, CharacterCard, 6 tests |

Status: `open | running | done | failed`

## Issues
- The run overview's `characterName` is replaced by a nested character object; the backend's own callers and the frontend fixtures follow.
- Ability modifiers on the review are browser arithmetic over numbers the backend fixed, not a rule the model invents.
- The seed hero has no alignment, speed or skills of its own; its review shows "—" there.
- glab is signed in as f4lkh3; human instruction: merge on my own when the sprint went without bigger issues, rebase from main before starting and before each merge.

## Backlog proposals

## Verify
Round 1: approve, no failed criteria (live in the browser incl. a real model failure).
