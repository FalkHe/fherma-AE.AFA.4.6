---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
stage: done
---
# Progress: Sprint 04

| WI | Status | Note |
|---|---|---|
| 1 | done | situation projection with private and public views, roles derived, recent window of 20 |
| 2 | done | recall_history expands anchors to their turn's player-visible events |

Status: `open | running | done | failed`

## Issues
- No qa agent, per owner's "reduce testing".

## Issues (gates)
- Gates passed first time (lint, 1247 unit, 184 database tests). Shared-file edits were again bundled into the other agent's commit.

## Backlog proposals
- A creature explicitly marked not hostile but still armed reads as an ally rather than neutral; revisit if the scheduler needs to tell "friendly" from "not attacking".

## Verify
Round 1: changes-requested — AC1 (derived roles: armed non-members defaulted to ally; goblins in the lair read as allies).
Round 2: approve, no failed criteria.
