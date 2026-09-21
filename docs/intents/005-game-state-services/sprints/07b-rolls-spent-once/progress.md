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
| 1 | done | the two consumers, `_consume_roll`, two 409 codes |
| 2 | done | `get_awaiting` and the events read's new shape |
| 3 | done | module doc §14/§15, README, the `cli.py` slip fixed |
| qa | done | 2 acceptance tests |

Status: `open | running | done | failed`

## Issues

- The second half of the split sprint 07; 07a is merged. This half spends a roll and adds `awaiting`.
- `GET …/events` changes shape, from a bare array to an object carrying the events and what is awaited. Nothing
  outside the backend reads it yet, so the blast radius is two existing tests. `frontend/src/api/schema.d.ts` is
  deliberately **not** regenerated — phase 9 owns that, and every playthrough route is already absent from it.
- Carried from 07a: the module README cites `playthrough/cli.py` for the roll command, which lives in
  `commands.py`. Already wrong on `main`; fixed here in passing.

- **A landed test from intent 004 began failing for a structural reason and was fixed here.** Its AC5 ran the whole
  engine-free suite in a subprocess with a hardcoded 120-second budget; the suite now takes about 128 seconds, so
  it timed out. Worse, it made the suite run itself — quadratic in suite size, and guaranteed to break again at any
  fixed timeout. It now nests a small fixed-cost run that still proves what the criterion is about: the `database`
  marker is registered and the engine-free default works in a fresh process. Unregistering the marker was confirmed
  to fail it. `make backend-test` drops from ~128s to about half that.

## Backlog proposals

<none yet>

## Verify
