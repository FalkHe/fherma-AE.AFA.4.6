---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
stage: draft
---
# Progress: Sprint 04

| WI | Status | Note |
|---|---|---|
| 1 | done | character, rename, archive/delete, activate, three 409 codes |
| 2 | done | three routes, wire schemas, `PATCH` added to CORS |
| 3 | done | general model lifecycle rows, README, playthrough doc |
| qa | done | 4 acceptance tests; AC3 sent back once for a leaking monkeypatch |

Status: `open | running | done | failed`

## Issues

- **The product owner amended the brief mid-sprint**, answering the two product-visible questions research raised:
  there is no unarchive at all — an archived game is kept only to re-read its story, never played on — a finished
  game may be archived, and archiving a never-started game deletes it silently. AC3's "flip `active|ready ↔
  archived`" is superseded. `decisions.md` does not cover unarchiving either way, so nothing there contradicts it;
  the amendment is recorded here and in `review.md`, and wants a decision line of its own.
- Archiving an already-archived game is a no-op answering success rather than a refusal — agent-level call: the
  player's intent is already satisfied.
- Archive answers 204 with no body, because a never-started game no longer exists to return.
- This plan runs ~40 words over the cap. The overflow is the interface contract, not scope creep — but sprint 04 is
  the largest in the intent and character creation could have been split from the run's shelf life.

## Backlog proposals

- Sprint 03's `except IntegrityError` in `start_campaign_run` is wider than the duplicate-key case it names; it
  should be narrowed to the unique constraint before more sprints copy it.
- `ProseText` has no maximum length while `objects.name` is `String(120)` — phase 7 feeds generated text there.

## Verify
