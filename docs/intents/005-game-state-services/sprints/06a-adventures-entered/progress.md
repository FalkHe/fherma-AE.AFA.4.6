---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
stage: draft
---
# Progress: Sprint 06a

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| 3 | open | |
| qa | open | |

Status: `open | running | done | failed`

## Issues

- **Sprint 06 was split into 06a and 06b** at the mechanic boundary, applying the precedent the product owner set
  for sprint 05 rather than asking again: entering an adventure and using an exit are two mechanics, and one
  sprint carried both plus a route, four error classes and two positioning statements. Research recommended the
  same line. 06b is issue #34, new; rows 08 and 09 now depend on 06b.
- Research raised one product-visible point: with the shipped one-adventure campaign a second entry always meets
  "nothing left to enter" first, so the "one is already active" refusal is unreachable until a campaign authors
  two or more adventures. Both refusals are in the approved criteria, so both ship; the second is tested against
  a fixture campaign. Flagged in `review.md`.
- Called, agent-level: `finish_campaign_run` stays inlined in 06b's `use_exit` rather than becoming a public
  function before a second caller exists.

## Backlog proposals

<none yet>

## Verify
