---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
stage: done
---
# Progress: Sprint 08

| WI | Status | Note |
|---|---|---|
| 1 | done | Start adventure enters and opens play with the one-shot flag |
| 2 | done | opening send without a player row; one-shot router flag |
| 3 | done | empty line while only dividers are recorded |
| 4 | done | play screen fires the opening once; READMEs |

Status: `open | running | done | failed`

## Issues
Human asked for speed last sprint; kept the same mode: minimal component tests, no qa agent, functionality over polish.
Assumed, as the brief scopes it: a seat with no hero still reads "Waiting on party" and cannot press "Start adventure"; taking the ready-made hero stays with the character-creation chat, character creation being out of scope.
Assumed: the opening turn is fired from the play screen, so the header names the scene at first paint; a failed enter keeps the player on the run screen with a retryable line.

## Backlog proposals

## Verify
Round 1: approve, no failed criteria. The merge request carries no approval state because the verifier's account may not approve its own merge request.
