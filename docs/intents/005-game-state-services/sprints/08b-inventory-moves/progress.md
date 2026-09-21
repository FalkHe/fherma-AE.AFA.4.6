---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
stage: draft
---
# Progress: Sprint 08b

| WI | Status | Note |
|---|---|---|
| 1 | done | take, drop, give, container looting, the `use_item` seam |
| 2 | done | module doc §18/§19 and README |
| qa | done | 3 acceptance tests |

Status: `open | running | done | failed`

## Issues

- The second half of the split sprint 08; 08a is merged and its one-action rule is reused unchanged. `drop` is
  already excluded from the action set there, and a test in 08a fails if anyone adds it back.
- **The product owner's ruling that a container in the scene can be looted lands here** as AC5: taking accepts an
  item whose owner is a non-creature object standing in the actor's scene, so Greenhollow's `stolen-fleece` comes
  out of the `wool-sack`. Taking from another creature stays refused. Without it the adventure's own quest loot
  would be unreachable.

- WI1 found a gap by mutation testing its own work: nothing caught disabling `take`'s one-action check, so it
  added a test for it. It also found and fixed a wrong assumption in that new test — `stolen-fleece` starts
  carried by `wool-sack`, not lying loose.

## Backlog proposals

<none yet>

## Verify
