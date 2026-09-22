---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: running
---
# Progress: Sprint 05

| WI | Status | Note |
|---|---|---|
| 1 | done | route, read hook, badge, shell width; 4 tests |
| 2 | done | party section, player card, invite tile |
| 3 | done | dialog + common:inDevelopment keys |
| qa | – | cut on request: no separate acceptance suite |

Status: `open | running | done | failed`

## Issues
- Sprint lead decided the two open questions from research rather than stopping: the status badge speaks the dashboard's words (New / In progress / Archived, with `finished` folding into Archived) so both screens agree, and the dialog reads D13's line literally with a title and a Close button.
- Sprint lead accepted the architect's two assumptions: the back link sits at the top of the page, not in the shared header (that bar belongs to every screen); a run whose campaign content is gone reads like not-found.
- A separate qa work item was cut on the human's instruction to keep test effort small; acceptance is checked in the browser.

## Backlog proposals

## Verify
- WI1's back link targets `/` (today's landing route); the campaigns page itself arrives in sprint 07.
- `useRunOverview` casts the generated response type: this endpoint's 422 is typed `HTTPValidationError` instead of the shared error envelope every auth endpoint uses — a backend schema gap worth a later look.
