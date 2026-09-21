---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
stage: draft
---
# Progress: Sprint 07b

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| 3 | open | |
| qa | open | |

Status: `open | running | done | failed`

## Issues

- The second half of the split sprint 07; 07a is merged. This half spends a roll and adds `awaiting`.
- `GET …/events` changes shape, from a bare array to an object carrying the events and what is awaited. Nothing
  outside the backend reads it yet, so the blast radius is two existing tests. `frontend/src/api/schema.d.ts` is
  deliberately **not** regenerated — phase 9 owns that, and every playthrough route is already absent from it.
- Carried from 07a: the module README cites `playthrough/cli.py` for the roll command, which lives in
  `commands.py`. Already wrong on `main`; fixed here in passing.

## Backlog proposals

<none yet>

## Verify
