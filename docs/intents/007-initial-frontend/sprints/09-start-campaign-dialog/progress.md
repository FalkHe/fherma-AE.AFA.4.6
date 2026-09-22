---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
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
- jsdom does not fold a nested interactive descendant into an element's accessible name the way Chrome does, so this class of defect passes the suite and is only catchable in a real browser. Worth a browser-level accessibility check if more dialogs arrive.
- Dialog panels sit lighter than the rest of the dark palette — both this dialog and the in-development one. One pass over dialog styling.
- The seeded catalogue holds one campaign, so the picker shows a single card on the running site.

## Verify
Round 1: changes requested — all six acceptance criteria passed; the dialog had no visible close control and the module README claimed one.
Round 2: changes requested — the close control was added inside `DialogTitle`, folding "Close" into the dialog's accessible name. Corrected after the verdict (the button is now a sibling of the title, verified in a real browser), but the two-round limit means the verdict stands and the merge request is a draft.
