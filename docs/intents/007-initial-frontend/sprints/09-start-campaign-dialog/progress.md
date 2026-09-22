---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: running
---
# Progress: Sprint 09

| WI | Status | Note |
|---|---|---|
| 1 | done | catalogue hook, create mutation, select dialog |
| qa | – | folded into WI1's tests |

Status: `open | running | done | failed`

## Issues
- The campaign catalogue hook stays in `modules/playthrough` rather than opening a frontend `content` module: it has one caller, and the project promotes shared code only once a second module needs it unchanged. When character creation needs the catalogue it moves as it is.
- Sprint 08 lost two verify rounds to a stale module README, so this sprint's work item carries the README update explicitly rather than leaving it to be caught in review.

## Backlog proposals

## Verify
