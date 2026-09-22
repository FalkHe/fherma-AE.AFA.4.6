---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: draft
---
# Progress: Sprint 05

| WI | Status | Note |
|---|---|---|
| 1 | done | routes, fixture, 5 route tests, client regenerated via app-cli export |
| qa | done | 3 acceptance tests over the HTTP app |

Status: `open | running | done | failed`

## Issues
- Conversation state is in-process memory only: a server restart or a second worker loses live conversations and the player starts over (D12 allows it; no table added).
- glab is signed in as f4lkh3; human instruction: merge on my own when the sprint went without bigger issues, rebase from main before starting and before each merge.

## Backlog proposals
- `make generate-api` targets `docker compose exec app-web`, which does not start on this machine (compose-up DNS for `postgres`), and its redirect truncates `frontend/openapi.json` on failure; export through `app-cli` instead or guard the redirect.

## Verify
Round 1: changes requested — AC3: `sheet.abilities` shows pre-racial draft scores while HP/AC/review/saved character use the final ones.
Round 1 fix: panel abilities come from the built sheet or `apply_race`; AC3 test asserts Halfling 15→17.
