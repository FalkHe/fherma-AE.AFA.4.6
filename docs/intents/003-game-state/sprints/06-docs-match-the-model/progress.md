---
author: sprint
owner: agent
created: 2026-09-17
updated: 2026-09-17
stage: draft
---
# Progress: Sprint 06

| WI | Status | Note |
|---|---|---|
| 1 | done | all 19 corrections plus the two decided departures, across the five general documents — 87eb003 |
| 2 | done | the module document and its index row — ae31fb5 |
| 3 | done | six roadmap rows closed, one file, twelve lines — 6e3c5c0 |

Status: `open | running | done | failed`

## Issues
- Two gaps in the correction list were decided rather than escalated. One use of the abandoned entity name is not on the list, but the criterion demands the name be gone everywhere, so it is corrected with the item nearest to it. And the list marks the purge row out of scope without saying whether to remove it or defer it: it is removed, and the promise that nothing is ever deleted is stated once instead.
- Removing the first known gap renumbers the rest. Nothing refers to them by number.

## Gates
`make lint` green · `make test` 671 backend + 53 frontend · `make backend-test-db` 32 passed. Nothing under `backend/` or `frontend/` is in the diff.

## Backlog proposals
Four things found while writing, all outside the 19-item correction list and therefore left alone, as the brief requires:
- The tool table in the general architecture document still lists starting combat and ending a round as tracking initiative, without marking it deferred. It is the one place in the general documents where initiative reads as a promise.
- A lifecycle row still says a campaign run generates the player's creature. It instantiates it from the seed player character; generating one is a later phase.
- The glossary says "seed character" in one entry where the agreed term is "seed player character".
- The glossary still heads two entries with entity nouns the agreed vocabulary avoids in prose. As head-words they may earn the exception.

## Verify
Round 1: approve — AC1-AC7 all OK. All 19 §7 items verified in the file each names, plus the two decided departures (`model.md:57`; the Purge row removed with D3 restated once). `grep -n Playthrough docs/general/` is empty; the three lower-case hits (`model.md:61`, `architecture.md:46`, `glossary.md:63`) are activity prose. `Encounter`/`Initiative` survive only where marked deferred (`model.md:175`, `glossary.md:16`, `:71`) — the one unmarked hit, `architecture.md:73`, is assigned to phase 8 by `roadmap/Stage-01/README.md:388`, so leaving it is correct, not a gap. AC5: `docs/modules/playthrough.md` matches `backend/app/modules/playthrough/models.py` column by column and states the empty surface (§8), which `ls` confirms (`__init__.py`, `models.py`, `README.md` only). AC6: `git diff main..HEAD -- docs/roadmap/` is 6 rows in one file, each original question intact with the closure appended. AC7: no path under `backend/` or `frontend/` in the diff.

MR: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/22
