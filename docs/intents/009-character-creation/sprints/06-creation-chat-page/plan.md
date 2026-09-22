---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 06

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 0 | backend-python | `CreationReply.readyMadeName` (the campaign's seed hero name, present on every reply of a conversation), regenerated spec + client | one route test extended: start reply carries "Rosalind Thorn" | – |
| 1 | frontend | Module `frontend/src/modules/character/` (route `/runs/:runId/create-character`, `useCreationChat`, transcript, composer, offered choices incl. "Take {name}" / "Make my own" at the gate, sheet panel with step indicator and narrow-screen strip, leave dialog, `character` locale namespace), route registration, run-screen "Create character" as a link, module README, six tests | AC1 button navigates to the page · AC2 greeting + player turn render, a choice button posts its own label · AC3 sheet panel shows set fields, "—" for empty, "Step 2 of 7", collapsed and not · AC4 back link opens the dialog, "Leave" lands on the run · AC5 `error: true` shows the in-voice line, "Try again" re-posts the same text · AC6 page copy equals the locale values | I1 (codes against it; typecheck once WI0's client lands) |

No qa work item (backlog: black-box tests only in sprint 05).

## Interfaces
- I1: `CreationReply` gains `readyMadeName: string | null` (sprint 05 contract otherwise unchanged); everything under `research.md → Interfaces` — route, `useCreationChat` return shape (plus `readyMadeName: string | null`), component props, `PartySection`/`PlayerCard` prop change, locale keys (plus `choices.takeReadyMade` with `{{name}}` and `choices.makeMyOwn`).
- Technical decisions 1, 3–7 of the research are binding; decision 2 is amended: the gate offer gets two buttons fed by `readyMadeName`.

## Order
Parallel: WI0, WI1 (WI1 waits for WI0's regenerated client before its final typecheck). Then gates.
